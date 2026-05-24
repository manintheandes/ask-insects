from pathlib import Path
import unittest


class DeployFilesTests(unittest.TestCase):
    def test_systemd_service_runs_hosted_server(self):
        text = Path("deploy/systemd/ask-insects.service").read_text(encoding="utf-8")

        self.assertIn("ASK_INSECTS_TOKEN", text)
        self.assertIn("python3 -m askinsects.server", text)
        self.assertIn("/home/josh/ask-insects", text)

    def test_deploy_scripts_use_gcloud_compute(self):
        vm = Path("scripts/deploy_gce_vm.sh").read_text(encoding="utf-8")
        app = Path("scripts/deploy_gce_app.sh").read_text(encoding="utf-8")

        self.assertIn("gcloud compute instances", vm)
        self.assertIn("gcloud compute ssh", app)
        self.assertIn("ask-insects", vm)
        self.assertIn("systemctl restart ask-insects", app)


if __name__ == "__main__":
    unittest.main()
