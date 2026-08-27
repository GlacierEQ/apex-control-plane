"""
APEX OCI CLOUD HORIZON PROVISIONER
Target: Oracle Cloud Infrastructure (OCI) Always-Free Ampere A1 Compute Instance
Role: Host 24/7 Sovereign Temporal Server and Manus/GitHub Webhook Endpoints
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


class OCITemporalProvisioner:
    """
    Automates deployment of the 24/7 Temporal Workflow Server onto OCI Always-Free tier.
    """

    DEFAULT_CONFIG_PATH = Path("/Users/kcbflux/.oci/config")
    CLOUD_INIT_PATH = Path(__file__).resolve().parent / "cloud_init_temporal.sh"

    @classmethod
    def load_oci_config(cls) -> Dict[str, str]:
        config_data = {}
        if not cls.DEFAULT_CONFIG_PATH.exists():
            return config_data

        for line in cls.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("["):
                k, v = line.split("=", 1)
                config_data[k.strip()] = v.strip()
        return config_data

    @classmethod
    def get_cloud_init_base64(cls) -> str:
        if cls.CLOUD_INIT_PATH.exists():
            content = cls.CLOUD_INIT_PATH.read_bytes()
            return base64.b64encode(content).decode("utf-8")
        return ""

    @classmethod
    def generate_launch_spec(cls) -> Dict[str, Any]:
        oci_cfg = cls.load_oci_config()
        return {
            "tenancy_id": oci_cfg.get("tenancy", ""),
            "user_id": oci_cfg.get("user", ""),
            "region": oci_cfg.get("region", "mx-monterrey-1"),
            "fingerprint": oci_cfg.get("fingerprint", ""),
            "shape": "VM.Standard.A1.Flex",
            "shape_config": {
                "ocpus": 4,
                "memory_in_gbs": 24,
            },
            "display_name": "apex-temporal-sovereign-head",
            "operating_system": "Canonical Ubuntu 22.04 LTS (aarch64)",
            "boot_volume_size_gbs": 100,
            "services": [
                "Temporal Workflow Engine (gRPC 7233)",
                "Temporal Web Console (Port 8080)",
                "PostgreSQL Database Backend (Port 5432)",
                "Asynchronous Webhook Ingress (Port 443)",
            ],
            "cloud_init_script": str(cls.CLOUD_INIT_PATH),
        }

    @classmethod
    def generate_oci_cli_command(cls) -> str:
        spec = cls.generate_launch_spec()
        cmd = [
            "oci compute instance launch",
            f"--compartment-id \"{spec['tenancy_id']}\"",
            f"--shape \"{spec['shape']}\"",
            f"--shape-config '{{\"ocpus\": 4, \"memoryInGBs\": 24}}'",
            f"--display-name \"{spec['display_name']}\"",
            f"--region \"{spec['region']}\"",
            f"--user-data-file \"{cls.CLOUD_INIT_PATH}\"",
            "--assign-public-ip true",
        ]
        return " \\\n  ".join(cmd)

    @classmethod
    def export_deployment_packet(cls, output_dir: Optional[Path] = None) -> Path:
        out_d = output_dir or Path(__file__).resolve().parent
        out_d.mkdir(parents=True, exist_ok=True)

        spec = cls.generate_launch_spec()
        manifest_file = out_d / "deployment_manifest.json"
        manifest_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")

        cli_script = out_d / "launch_instance.sh"
        cli_script.write_text(f"#!/usr/bin/env bash\n\n{cls.generate_oci_cli_command()}\n", encoding="utf-8")
        cli_script.chmod(0o755)

        return manifest_file


if __name__ == "__main__":
    packet = OCITemporalProvisioner.export_deployment_packet()
    print("=" * 70)
    print("⚡ APEX OCI TEMPORAL SERVER DEPLOYMENT PACKET EXPORTED")
    print(f"Manifest: {packet}")
    print(f"CLI Launch Script: {packet.parent / 'launch_instance.sh'}")
    print("=" * 70)
