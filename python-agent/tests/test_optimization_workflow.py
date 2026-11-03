import importlib
from pathlib import Path


def test_graph_repairs_build_then_reviews_builds_accepts_and_publishes(tmp_path, monkeypatch):
    wf=importlib.import_module("workflow.code_gen_workflow")
    monkeypatch.setattr(wf.config,"CODE_OUTPUT_DIR",str(tmp_path))
    calls=[]
    def phase(name, output):
        def run(state):
            calls.append(name)
            return {**state,**output}
        return run
    monkeypatch.setattr(wf,"intent_agent",phase("intent",{"phase":"intent_done"}))
    monkeypatch.setattr(wf,"pm_agent",phase("pm",{"phase":"prd_done","prd":{}}))
    monkeypatch.setattr(wf,"architect_agent",phase("arch",{"phase":"arch_done","architecture":{"file_list":[{"path":"index.html"}]}}))
    monkeypatch.setattr(wf,"image_collector_agent",phase("image",{"images":[]}))
    def coder(state):
        calls.append("coder")
        content="<h1>Working app</h1>"
        Path(state["project_dir"],"index.html").write_text(content)
        return {**state,"phase":"code_done","code_files":[{"path":"index.html","content":content}]}
    monkeypatch.setattr(wf,"coder_agent",coder)
    monkeypatch.setattr(wf,"reviewer_agent",phase("review",{"phase":"review_done","review":{"passed":True,"score":95,"issues":[]}}))
    def build(state):
        calls.append("build")
        result={"status":"failed","success":False,"failure_kind":"code","log":"index.html:1 fix entry"} if calls.count("build")==1 else {"status":"not_required","success":None,"log":"static"}
        return {**state,"phase":"build_done","build_result":result}
    monkeypatch.setattr(wf,"builder_agent",build)
    result=wf.run_workflow("普通页面",app_id="",code_gen_type="html")
    assert result["final_status"]=="success"
    assert result["artifact_status"]=="published"
    assert result["build_repair_count"]==1
    assert calls.count("coder")==calls.count("review")==calls.count("build")==2
    assert result["runtime_result"]["status"]=="succeeded"
    assert Path(result["project_dir"],"index.html").read_text()=="<h1>Working app</h1>"
