"""完整测试：Coder → Reviewer 链路"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_reviewer_real():
    from agents.coder_agent import coder_agent
    from agents.reviewer_agent import reviewer_agent
    from agents.supervisor_agent import supervisor_decision

    # Step 1: Prepare architecture + generate code
    arch = {
        "tech_stack": {"framework": "Vue 3"},
        "component_tree": [
            {"name": "App", "description": "Root app", "props": [], "children": ["Header"]},
            {"name": "Header", "description": "Top nav bar", "props": ["title: string"], "children": []},
        ],
        "file_list": [
            {"path": "src/App.vue", "description": "Root component with router-view", "file_type": "page"},
            {"path": "src/components/Header.vue", "description": "Navigation header", "file_type": "component", "component_name": "Header"},
        ],
        "data_flow": [{"from_component": "App", "to_component": "Header", "data_type": "title: string", "mechanism": "props"}],
    }
    prd = {
        "page_name": "Test Page", "page_type": "landing",
        "features": [
            {"name": "Header Nav", "description": "Top navigation bar", "priority": "high", "interactions": ["click nav links"]},
        ],
        "target_audience": "all", "color_preference": "blue+white",
        "layout_type": "single-column", "data_dependencies": [],
    }
    state = {"architecture": arch, "prd": prd, "phase": "arch_done", "retry_count": 0, "max_retries": 3}

    print("Step 1: Coder Agent...")
    state = coder_agent(state)
    assert state["phase"] == "code_done", f"Coder failed: {state.get('error')}"
    files = state["code_files"]
    print(f"  Generated {len(files)} files")

    # Step 2: Review
    print("Step 2: Reviewer Agent...")
    state = reviewer_agent(state)
    assert state["phase"] == "review_done", f"Reviewer failed: {state.get('error')}"
    review = state["review"]
    print(f"  Score: {review['score']}/100, passed={review['passed']}, retry_count={state['retry_count']}")
    print(f"  Issues: {len(review.get('issues', []))}")
    for iss in review.get("issues", [])[:3]:
        print(f"    - [{iss['severity']}] {iss['file']}: {iss['description'][:60]}...")

    # Step 3: Supervisor routing
    next_node = supervisor_decision(state)
    print(f"Step 3: Supervisor routes to: {next_node}")

    if not review["passed"] and state["retry_count"] < 3:
        assert next_node == "coder_agent", f"Should retry coder, got: {next_node}"
        print("Retry logic WORKING: will re-invoke coder_agent with review context")
    elif review["passed"]:
        assert next_node == "builder_agent", f"Should go to builder, got: {next_node}"
        print("Pass logic WORKING: will proceed to builder")

    print("=== REVIEWER FULL TEST PASSED ===")

if __name__ == "__main__":
    test_reviewer_real()
