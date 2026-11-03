"""Bound per-request input without resetting the cumulative execution budget."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict
from benchmark.redaction import redact


class ContextWindowExceeded(RuntimeError):
    pass


def input_bound(messages, schemas=''):
    return sum(len(json.dumps(item, ensure_ascii=False, default=str).encode()) + 32
               for item in messages_to_dict(messages)) + len(schemas.encode()) + 256


def message_groups(messages):
    """An assistant tool batch and every matching result are indivisible."""
    groups = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if isinstance(message, ToolMessage):
            raise ContextWindowExceeded('orphan_tool_result; progress retained')
        group = [message]
        index += 1
        calls = getattr(message, 'tool_calls', [])
        if calls:
            expected = {call['id'] for call in calls}
            found = []
            while index < len(messages) and isinstance(messages[index], ToolMessage):
                found.append(messages[index].tool_call_id)
                group.append(messages[index])
                index += 1
            if len(found) != len(expected) or set(found) != expected:
                raise ContextWindowExceeded('incomplete_tool_batch; progress retained')
        groups.append(group)
    return groups


def describe_groups(groups):
    operations, decisions = [], []
    for group in groups:
        for message in group:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    operations.append({'tool': call['name'], 'path': call.get('args', {}).get('path'), 'tool_call_id': call['id']})
                if message.content:
                    decisions.append(str(message.content)[:1000])
    return operations, decisions


class CoderContext:
    def __init__(self, state, tools):
        self.state = state
        self.window = int(os.getenv('HARNESS_CONTEXT_WINDOW_TOKENS', '65536'))
        self.output_reserve = int(os.getenv('HARNESS_CONTEXT_OUTPUT_RESERVE', '8192'))
        if self.output_reserve < 1 or self.window <= self.output_reserve:
            raise ContextWindowExceeded('invalid_context_capacity_or_output_reserve')
        self.keep = max(1, min(8, int(os.getenv('HARNESS_CONTEXT_RECENT_GROUPS', '2'))))
        self.schemas = json.dumps([{'name': t.name, 'description': t.description, 'parameters': t.args_schema.model_json_schema()
                                   if t.args_schema and not isinstance(t.args_schema, dict) else t.args_schema}
                                  for t in tools], ensure_ascii=False)
        key = hashlib.sha256((str(Path(state['project_dir']).resolve()) + state.get('artifact_run_id', '')).encode()).hexdigest()[:24]
        self.directory = Path(state['project_dir']).parent / '.harness-context' / key
        self.directory.mkdir(parents=True, exist_ok=True)
        self.report = state.setdefault('context_report', {'compactions': 0, 'requests': [],
            'estimate_method': 'UTF-8 serialized byte upper bound; not measured tokenizer usage',
            'summary_model_calls': 0, 'summaries': []})

    def constraints(self):
        contract = self.state.get('acceptance_contract')
        return HumanMessage(content='## Current task and protected constraints\n' + json.dumps({
            'goal': self.state.get('user_request'), 'acceptance_contract': contract,
            'mode': self.state.get('mode'),
            'allowed_changes': self.state.get('change_plan'),
            'latest_correction': self.state.get('active_instructions', []),
            'current_error': self.state.get('coder_current_error') or self.state.get('build_repair_context'),
            'review_issues': (self.state.get('review') or {}).get('issues', []),
            'discussion_decisions': (self.state.get('review') or {}).get('autogen_context'),
            'verified_repair_references': self.state.get('repair_experiences', []),
            'file_truth': '摘要记录过去的操作；编辑前重新读取真实文件和哈希。不得把摘要当作当前文件内容。',
        }, ensure_ascii=False), id='harness-current-constraints')

    def record(self, messages, suffix='raw'):
        sequence = len(self.report['requests']) + 1
        path = self.directory / f'request-{sequence:05d}.{suffix}.json'
        payload = {'sequence': sequence, 'prompt_version': 'harness-context-v1',
                   'messages': redact(messages_to_dict(messages))}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        return str(path)

    def prepare(self, messages):
        from workflow.budget import active_budget
        budget = active_budget.get()
        if budget:
            budget.check()
        # Refresh protected constraints on every request, including after steering.
        rest = [m for m in messages[1:] if getattr(m, 'id', None) != 'harness-current-constraints']
        result = [messages[0], self.constraints(), *rest]
        reference = self.record(result)
        before = input_bound(result, self.schemas)
        limit = self.window - self.output_reserve
        if before > limit:
            groups = message_groups(rest)
            has_tools = any(getattr(m, 'tool_calls', []) for group in groups for m in group)
            keep = min(self.keep, max(1 if has_tools else 0, len(groups) - 1))
            removed = groups[:-keep] if keep else groups
            operations, decisions = describe_groups(removed)
            prior = self.report.get('last_handoff', {})
            summary = {'goal': self.state.get('user_request'), 'constraints': 'See protected current constraints above',
                       'observed_operations': (prior.get('observed_operations', []) + operations)[-80:],
                       'decisions_excerpt': (prior.get('decisions_excerpt', []) + decisions)[-8:],
                       'validation': self.state.get('runtime_result') or self.state.get('build_result'),
                       'required_files': [f.get('path') for f in (self.state.get('architecture') or {}).get('file_list', [])],
                       'remaining': '按合同完成尚未验证的工作；修改前重新读取文件，不根据历史摘要覆盖文件。',
                       'raw_records': (prior.get('raw_records', []) + [reference])[-20:],
                       'next_step': '继续最近的完整工具批次；需要旧细节时通过文件读取/代码搜索定位。'}
            retained = [m for group in (groups[-keep:] if keep else []) for m in group]
            handoff = HumanMessage(content='## Structured progress handoff\n' + json.dumps(summary, ensure_ascii=False), id='harness-handoff')
            result = [messages[0], self.constraints(), handoff, *retained]
            while input_bound(result, self.schemas) > limit and keep > 1:
                keep -= 1
                operations, decisions = describe_groups(groups[:-keep])
                summary['observed_operations'] = (prior.get('observed_operations', []) + operations)[-80:]
                summary['decisions_excerpt'] = (prior.get('decisions_excerpt', []) + decisions)[-8:]
                handoff = HumanMessage(content='## Structured progress handoff\n' + json.dumps(summary, ensure_ascii=False), id='harness-handoff')
                result = [messages[0], self.constraints(), handoff, *[m for g in groups[-keep:] for m in g]]
            self.report['last_handoff'] = summary
            self.report['compactions'] += 1
            self.report['summaries'].append({'raw_reference': reference, 'before_input_bound': before,
                                            'after_input_bound': input_bound(result, self.schemas)})
        after = input_bound(result, self.schemas)
        self.report['requests'].append({'raw_reference': reference, 'input_bound': after,
                                       'input_reference': self.record(result, 'input'),
                                       'window': self.window, 'output_reserve': self.output_reserve})
        if after > limit:
            self.report['stop_reason'] = 'context_window_exhausted'
            raise ContextWindowExceeded('context_window_exhausted; saved progress: ' + reference)
        return result

    def observe(self, response):
        usage = getattr(response, 'usage_metadata', None)
        if self.report['requests']:
            self.report['requests'][-1]['provider_usage'] = usage if isinstance(usage, dict) else None
