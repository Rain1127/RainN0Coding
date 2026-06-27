import unittest


class WorkflowImportTest(unittest.TestCase):
    def test_code_gen_workflow_imports_builder_agent(self):
        from workflow.code_gen_workflow import create_code_gen_workflow

        self.assertTrue(callable(create_code_gen_workflow))


if __name__ == "__main__":
    unittest.main()
