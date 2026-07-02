"""Tests for the Transform Graph Engine."""
import unittest
from coreai_catalog.transform_graph import TransformGraph, PipelineStage, Pipeline


class TestTransformGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_graph_has_inputs(self):
        """Graph recognizes known input modalities."""
        inputs = self.graph.input_modalities
        self.assertIn("text", inputs)
        self.assertIn("image", inputs)
        self.assertIn("audio", inputs)

    def test_graph_has_outputs(self):
        """Graph recognizes known output modalities."""
        outputs = self.graph.output_modalities
        self.assertIn("text", outputs)
        self.assertIn("audio", outputs)
        self.assertIn("image", outputs)

    def test_direct_edge_exists(self):
        """text -> audio is a direct edge (TTS models)."""
        edges = self.graph.get_edges("text", "audio")
        self.assertGreater(len(edges), 0)
        for edge in edges:
            self.assertTrue(edge.model_id)
            self.assertEqual(edge.input_modality, "text")
            self.assertEqual(edge.output_modality, "audio")

    def test_no_direct_edge(self):
        """audio -> image requires multi-hop (no direct edge)."""
        edges = self.graph.get_edges("audio", "image")
        self.assertEqual(len(edges), 0)

    def test_all_edges_for_input(self):
        """All output modalities reachable from text in 1 hop."""
        edges = self.graph.get_all_edges_from("text")
        output_mods = {e.output_modality for e in edges}
        self.assertIn("text", output_mods)
        self.assertIn("audio", output_mods)
        self.assertIn("image", output_mods)
        self.assertIn("vector", output_mods)

    def test_edge_count_matches_catalog(self):
        """Total direct edges should match known count (~29 unique modality pairs)."""
        all_pairs = self.graph.get_all_modality_pairs()
        self.assertGreaterEqual(len(all_pairs), 25)


class TestShortestPath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_direct_path(self):
        """text -> audio should be 1 hop."""
        pipeline = self.graph.shortest_path("text", "audio")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 1)
        self.assertEqual(pipeline.modality_chain, ["text", "audio"])

    def test_two_hop_path(self):
        """audio -> image requires 2 hops (audio -> text -> image)."""
        pipeline = self.graph.shortest_path("audio", "image")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 2)
        self.assertEqual(pipeline.modality_chain, ["audio", "text", "image"])

    def test_three_hop_path(self):
        """audio -> classes requires 3 hops."""
        pipeline = self.graph.shortest_path("audio", "classes")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 3)

    def test_no_path(self):
        """query -> image should return None (no route exists)."""
        pipeline = self.graph.shortest_path("query", "image")
        self.assertIsNone(pipeline)

    def test_same_modality(self):
        """text -> text should be 1 hop."""
        pipeline = self.graph.shortest_path("text", "text")
        self.assertIsNotNone(pipeline)
        self.assertEqual(pipeline.hop_count, 1)

    def test_pipeline_has_model_info(self):
        """Each stage references a real model with metadata."""
        pipeline = self.graph.shortest_path("image", "audio")
        self.assertIsNotNone(pipeline)
        for stage in pipeline.stages:
            self.assertTrue(stage.model_id)
            self.assertTrue(stage.model_name)
            self.assertTrue(stage.runner)


class TestReachability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from coreai_catalog.catalog import Catalog
        cat = Catalog()
        cls.graph = TransformGraph(cat.models, cat)

    def test_reachable_outputs_from_text(self):
        reachable = self.graph.reachable_outputs("text")
        self.assertIn("text", reachable)
        self.assertIn("audio", reachable)
        self.assertIn("image", reachable)
        self.assertIn("vector", reachable)
        self.assertGreaterEqual(len(reachable), 15)

    def test_reachable_outputs_from_document_image(self):
        reachable = self.graph.reachable_outputs("document_image")
        self.assertIn("html", reachable)
        self.assertIn("markdown", reachable)

    def test_unreachable(self):
        reachable = self.graph.reachable_outputs("query")
        self.assertNotIn("image", reachable)

    def test_all_paths_text_to_audio(self):
        pipelines = self.graph.all_paths("text", "audio", max_hops=2)
        self.assertGreater(len(pipelines), 1)

    def test_all_paths_limited(self):
        pipelines = self.graph.all_paths("text", "classes", max_hops=1)
        self.assertEqual(len(pipelines), 0)

    def test_full_matrix(self):
        matrix = self.graph.reachability_matrix()
        total = sum(len(targets) for targets in matrix.values())
        self.assertGreaterEqual(total, 45)


if __name__ == "__main__":
    unittest.main()
