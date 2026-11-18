import multiprocessing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from cloud_continuity_corpus import ingest_cloud_snapshot, recover_cloud_context


def worker(root, index, barrier, queue):
    try:
        barrier.wait(timeout=10)
        ingest_cloud_snapshot(Path(root), [{
            "provider": "drive", "account": "operator", "native_id": f"file-{index}",
            "revision": "r1", "namespace": "architecture", "title": f"File {index}",
            "url": f"https://drive.google.com/file/d/{index}/view",
            "extracted_text": f"evidence-{index}",
        }])
        queue.put(None)
    except Exception as exc:
        queue.put(repr(exc))


class CloudConcurrentIngestionTests(TestCase):
    def test_parallel_writers_preserve_all_revisions_and_readback(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "corpus"
            root.mkdir(mode=0o700)
            ctx = multiprocessing.get_context("spawn")
            barrier = ctx.Barrier(6)
            queue = ctx.Queue()
            processes = [ctx.Process(target=worker, args=(str(root), i, barrier, queue))
                         for i in range(6)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual([queue.get(timeout=2) for _ in processes], [None] * 6)
            result = recover_cloud_context(
                root, namespace="architecture",
                required_source_ids=[f"drive:operator:file-{i}" for i in range(6)])
            self.assertEqual(len(result["sources"]), 6)
            self.assertEqual({s["text"] for s in result["sources"]},
                             {f"evidence-{i}" for i in range(6)})
