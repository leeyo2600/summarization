import unittest
from unittest.mock import patch
import torch
from webapp.departments import embedding_device, cosine_max


class GpuTests(unittest.TestCase):
    def test_auto_device(self):
        for available,expected in ((True,'cuda'),(False,'cpu')):
            with patch('torch.cuda.is_available',return_value=available):
                self.assertEqual(embedding_device(),expected)

    def test_cosine_on_cpu_and_multiple_query_chunks(self):
        queries=torch.tensor([[1.,0.]]*40+[[0.,1.]])
        documents=torch.tensor([[1.,0.],[0.,1.],[-1.,0.]])
        self.assertEqual(cosine_max(queries,documents),[1.,1.,0.])

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA runtime unavailable')
    def test_cuda_matches_cpu(self):
        queries=torch.nn.functional.normalize(torch.randn(40,16),dim=1)
        documents=torch.nn.functional.normalize(torch.randn(80,16),dim=1)
        actual=cosine_max(queries.cuda(),documents.cuda())
        expected=cosine_max(queries,documents)
        torch.testing.assert_close(torch.tensor(actual),torch.tensor(expected),rtol=1e-5,atol=1e-5)
