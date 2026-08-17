import numpy as np, pytest, uuid
from app.services.raster_processing import ndvi,coverage_percent,RasterProcessingError
from app.schemas.tool_evidence import ToolEvidence,EvidenceSourceRef

def test_ndvi_is_deterministic():
 out=ndvi(np.array([[1.,2.]]),np.array([[3.,2.]])); assert np.allclose(out,[[0.5,0.0]],equal_nan=True)
def test_ndvi_rejects_shape_mismatch():
 with pytest.raises(RasterProcessingError): ndvi([1,2],[1])
def test_coverage(): assert coverage_percent([[True,False],[True,True]])==75.0
def test_measured_evidence_requires_determinism():
 with pytest.raises(ValueError): ToolEvidence(project_id=uuid.uuid4(),tool_name='x',deterministic=False,status='measured',payload={},sources=[EvidenceSourceRef(kind='raster_dataset',id=uuid.uuid4())])
def test_retrieved_evidence_requires_source():
 with pytest.raises(ValueError): ToolEvidence(project_id=uuid.uuid4(),tool_name='x',deterministic=False,status='retrieved',payload={})
