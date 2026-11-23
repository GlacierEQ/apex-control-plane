"""MCP transport and causal owner-local recovery tests."""
import io
import json
import os
import unittest
from unittest.mock import patch
from scripts import continuity_mcp_stdio as m


def req(method, params=None, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": method,
            "params": params or {}}

class MCPTests(unittest.TestCase):
    def test_protocol_and_tool_registration(self):
        self.assertEqual(m.handle(req("initialize"))["protocolVersion"], m.PROTOCOL)
        self.assertEqual(m.handle(req("tools/list"))["tools"][0]["name"], m.TOOL)
        self.assertEqual(m.handle(req("ping")), {})

    def test_notification_cannot_execute_mission_recovery(self):
        from scripts.continuity_mcp_stdio import handle, TOOL
        for identifier in (None, True, False, [], {}):
            request = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": TOOL, "arguments": {"session_id": "s", "invocation_id": "i"}}}
            if identifier is not None:
                request["id"] = identifier
            invoked = []
            with self.assertRaises(ValueError):
                handle(request, recover=lambda **kwargs: invoked.append(kwargs))
            self.assertEqual(invoked, [])

    def test_invalid_ids_rejected_before_any_recovery(self):
        for value in ("../secret", "a:b", "", " bad ", "a"*129):
            with self.assertRaises(ValueError):
                m.handle(req("tools/call", {"name": m.TOOL,
                        "arguments": {"session_id": value, "invocation_id": "i"}}))

    def test_missing_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "configuration"):
                m.handle(req("tools/call", {"name": m.TOOL,
                    "arguments": {"session_id": "s", "invocation_id": "i"}}))

    def test_owner_consumer_causally_selected(self):
        with patch.object(m, "_config", return_value=[__import__("pathlib").Path(__file__)]*3), \
             patch.object(m, "enter", return_value={"status": "MISSION_CONTEXT_READY",
                "session_id": "s", "invocation_id": "i", "packet_digest": "sha256:" + "a" * 64,
                "native_chatgpt_startup_verified": False,
                "context": {"recovered_cursor": "continue:actual",
                            "next_transition": "RESUME_FROM_VERIFIED_CURSOR",
                            "native_chatgpt_startup_verified": False,
                            "source_evidence": [{"source_id": "drive:doc", "text_sha256": "b" * 64}]}}) as consumer, \
             patch("pathlib.Path.is_dir", return_value=True):
            out = m.handle(req("tools/call", {"name": m.TOOL,
                "arguments": {"session_id": "s", "invocation_id": "i"}}))
        self.assertEqual(out["structuredContent"]["context"]["recovered_cursor"], "continue:actual")
        self.assertEqual(consumer.call_count, 1)

    def test_forged_success_without_causal_evidence_denied(self):
        base = {"status": "MISSION_CONTEXT_READY", "session_id": "s",
                "invocation_id": "i", "packet_digest": "sha256:" + "a" * 64,
                "native_chatgpt_startup_verified": False,
                "context": {"recovered_cursor": "continue:real",
                            "next_transition": "RESUME_FROM_VERIFIED_CURSOR",
                            "native_chatgpt_startup_verified": False,
                            "source_evidence": [{"source_id": "drive:doc", "text_sha256": "b" * 64}]}}
        import copy
        for mutate in (
            lambda r: r.update(session_id="other"),
            lambda r: r.update(packet_digest="sha256:invalid"),
            lambda r: r["context"].update(source_evidence=[]),
            lambda r: r["context"].update(recovered_cursor=""),
            lambda r: r["context"].update(source_evidence=[{"source_id": "x"}]),
            lambda r: r["context"]["source_evidence"][0].update(text_sha256="abc"),
            lambda r: r["context"]["source_evidence"][0].update(text_sha256="g" * 64),
            lambda r: r["context"]["source_evidence"][0].update(text_sha256="A" * 64),
            lambda r: r["context"].update(native_chatgpt_startup_verified=True),
        ):
            forged = copy.deepcopy(base)
            mutate(forged)
            with patch.object(m, "_config", return_value=[__import__("pathlib").Path(__file__)]*3), \
                 patch("pathlib.Path.is_dir", return_value=True):
                with self.assertRaisesRegex(ValueError, "not verified"):
                    m.handle(req("tools/call", {"name": m.TOOL,
                        "arguments": {"session_id": "s", "invocation_id": "i"}}),
                        recover=lambda **kwargs: forged)

    def test_unverified_recovery_denied(self):
        with patch.object(m, "_config", return_value=[__import__("pathlib").Path(__file__)]*3), \
             patch.object(m, "enter", return_value={"status": "HALTED"}), \
             patch("pathlib.Path.is_dir", return_value=True):
            with self.assertRaisesRegex(ValueError, "not verified"):
                m.handle(req("tools/call", {"name": m.TOOL,
                    "arguments": {"session_id": "s", "invocation_id": "i"}}))

    def test_stdio_frames_and_errors(self):
        source = io.StringIO(json.dumps(req("initialize")) + "\n" +
                             json.dumps(req("unknown", request_id=2)) + "\n")
        target = io.StringIO()
        m.serve(source, target)
        frames = [json.loads(x) for x in target.getvalue().splitlines()]
        self.assertEqual(frames[0]["result"]["serverInfo"]["name"], "glaciereq-continuity-owner")
        self.assertEqual(frames[1]["error"]["code"], -32603)


    def test_malformed_frame_never_reuses_previous_request_identity(self):
        # A bad frame after an accepted session request must not impersonate it.
        source = io.StringIO(
            json.dumps(req("ping", request_id="previous")) + "\n"
            + "{broken-json\n"
            + json.dumps(req("ping", request_id="next")) + "\n"
        )
        target = io.StringIO()
        m.serve(source, target)
        frames = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual([frame["id"] for frame in frames],
                         ["previous", None, "next"])
        self.assertEqual(frames[1]["error"]["code"], -32700)
        self.assertEqual(frames[2]["result"], {})


    def test_ambiguous_frames_rejected_without_dispatch(self):
        frames = [
            '{"jsonrpc":"2.0","id":"old","id":"forged","method":"ping"}',
            '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"x","name":"y"}}',
            '{"jsonrpc":"2.0","id":NaN,"method":"ping"}',
            '{"jsonrpc":"2.0","id":Infinity,"method":"ping"}',
        ]
        source = io.StringIO("\n".join(frames) + "\n" +
                             json.dumps(req("ping", request_id="fresh")) + "\n")
        target = io.StringIO()
        with patch.object(m, "handle", wraps=m.handle) as dispatch:
            m.serve(source, target)
        out = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual([frame["id"] for frame in out], [None] * 4 + ["fresh"])
        self.assertTrue(all(frame["error"]["code"] == -32700 for frame in out[:4]))
        self.assertEqual(out[-1]["result"], {})


if __name__ == "__main__":
    unittest.main()
