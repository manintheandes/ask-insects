from pathlib import Path
import unittest


class DeployFilesTests(unittest.TestCase):
    def test_systemd_service_runs_hosted_server(self):
        text = Path("deploy/systemd/ask-insects.service").read_text(encoding="utf-8")

        self.assertIn("ASK_INSECTS_TOKEN", text)
        self.assertIn("python3 -m askinsects.server", text)
        self.assertIn("/home/josh/ask-insects", text)
        self.assertIn("--host 127.0.0.1", text)
        self.assertNotIn("--host 0.0.0.0", text)

    def test_deploy_scripts_use_gcloud_compute(self):
        vm = Path("scripts/deploy_gce_vm.sh").read_text(encoding="utf-8")
        app = Path("scripts/deploy_gce_app.sh").read_text(encoding="utf-8")

        self.assertIn("gcloud compute instances", vm)
        self.assertIn("gcloud compute ssh", app)
        self.assertIn("ask-insects", vm)
        self.assertIn("firewall-rules delete ask-insects-8080", vm)
        self.assertNotIn("--allow tcp:8080", vm)
        self.assertIn("systemctl restart ask-insects", app)
        self.assertIn("chmod 600", app)
        self.assertIn("http://127.0.0.1:8080/health", app)

    def test_private_tunnel_scripts_are_repo_owned(self):
        run = Path("scripts/run_hosted_tunnel.sh").read_text(encoding="utf-8")
        install = Path("scripts/install_hosted_tunnel_launchd.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("gcloud", run)
        self.assertIn("-L", run)
        self.assertIn("127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}", run)
        self.assertIn("ExitOnForwardFailure=yes", run)
        self.assertIn("ServerAliveInterval=30", run)
        self.assertIn("com.openinsects.ask-insects-tunnel", install)
        self.assertIn("launchctl bootstrap", install)
        self.assertIn("KeepAlive", install)


if __name__ == "__main__":
    unittest.main()
