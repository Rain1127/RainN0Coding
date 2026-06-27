import os
import tempfile
import unittest


class PathGuardTest(unittest.TestCase):
    def test_resolves_file_inside_project(self):
        from tools.path_guard import resolve_project_path

        with tempfile.TemporaryDirectory() as project_dir:
            full_path = resolve_project_path(project_dir, "src/App.vue")
            self.assertEqual(
                os.path.normcase(full_path),
                os.path.normcase(os.path.join(project_dir, "src", "App.vue")),
            )

    def test_rejects_parent_directory_escape(self):
        from tools.path_guard import resolve_project_path

        with tempfile.TemporaryDirectory() as project_dir:
            with self.assertRaises(ValueError):
                resolve_project_path(project_dir, "../outside.txt")

    def test_rejects_sibling_prefix_escape(self):
        from tools.path_guard import resolve_project_path

        with tempfile.TemporaryDirectory() as base_dir:
            project_dir = os.path.join(base_dir, "app")
            os.makedirs(project_dir)
            with self.assertRaises(ValueError):
                resolve_project_path(project_dir, "../app-other/secret.txt")


if __name__ == "__main__":
    unittest.main()
