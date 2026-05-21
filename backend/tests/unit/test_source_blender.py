import pytest
from services.source_blender import SourceBundle, _fetch_dbpedia
import httpx
from types import SimpleNamespace

def test_source_bundle_validity():
    # Empty bundle
    b1 = SourceBundle()
    assert not b1.is_valid
    
    # Only structured
    b2 = SourceBundle(structured_facts=["Fact 1"])
    assert not b2.is_valid
    
    # Only narrative
    b3 = SourceBundle(narrative="This is a very long narrative that should definitely be over forty characters long to pass the check.")
    assert not b3.is_valid
    
    # Both
    b4 = SourceBundle(
        structured_facts=["Fact 1"],
        narrative="This is a very long narrative that should definitely be over forty characters long to pass the check."
    )
    assert b4.is_valid

@pytest.mark.asyncio
async def test_fetch_dbpedia_success():
    class MockClient:
        async def get(self, *args, **kwargs):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"results": {"bindings": [
                    {"name": {"value": "France"}, "abstract": {"value": "France is a country. It is in Europe."}}
                ]}}
            )
    
    client = MockClient()
    facts = await _fetch_dbpedia("Geography", client)
    assert len(facts) == 1
    assert facts[0] == "France: France is a country." # Only first sentence is kept

@pytest.mark.asyncio
async def test_fetch_dbpedia_failure():
    class MockClient:
        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=500)
    
    client = MockClient()
    facts = await _fetch_dbpedia("Geography", client)
    assert facts == [] # Graceful fallback
