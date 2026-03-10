#!/usr/bin/env python3
"""
Test Script - Memory Enhancement Phases 4-5
Tests Multimodal Ingest and Enhanced Search

Run on ERPNext bench:
bench console --site [site]
exec(open('test_phase4_5.py').read())
"""
import frappe
import json

def run_tests():
    """Run all tests"""
    print("="*60)
    print("MEMORY ENHANCEMENT PHASE 4-5 TESTS")
    print("="*60)
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "tests": []
    }
    
    user = "fcrm@amb-wellness.com"
    
    # ============================================================
    # PHASE 4: MULTIMODAL INGEST TESTS
    # ============================================================
    print("\n--- PHASE 4: Multimodal Ingest ---")
    
    # Test 4.1: Import MultimodalIngest
    try:
        from raven_ai_agent.api.multimodal_ingest import MultimodalIngest
        print("✅ 4.1: MultimodalIngest import successful")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 4.1: Import failed - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 4.2: Create ingest instance
    try:
        ingest = MultimodalIngest(user=user)
        print("✅ 4.2: MultimodalIngest instance created")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 4.2: Instance creation failed - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 4.3: Ingest image URL
    try:
        result = ingest.ingest_file(
            "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=400",
            "image/png",
            "What's in this image?"
        )
        has_description = "description" in result or "summary" in result
        if has_description:
            print(f"✅ 4.3: Image ingest successful")
            print(f"   → {result.get('description', result.get('summary', ''))[:60]}...")
            results["passed"] += 1
        else:
            print(f"❌ 4.3: Image ingest failed - {result}")
            results["failed"] += 1
    except Exception as e:
        print(f"❌ 4.3: Image ingest error - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # ============================================================
    # PHASE 5: ENHANCED SEARCH TESTS
    # ============================================================
    print("\n--- PHASE 5: Enhanced Search ---")
    
    # Test 5.1: Import EnhancedSearch
    try:
        from raven_ai_agent.api.enhanced_search import EnhancedSearch
        print("✅ 5.1: EnhancedSearch import successful")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 5.1: Import failed - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 5.2: Create search instance
    try:
        search = EnhancedSearch(user=user)
        print("✅ 5.2: EnhancedSearch instance created")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 5.2: Instance creation failed - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 5.3: Search with scoring
    try:
        search_results = search.search_with_scoring("test", min_confidence=0.1)
        has_results = len(search_results) > 0
        has_scores = all("relevance_score" in r for r in search_results)
        has_citations = all("citation" in r for r in search_results)
        
        if has_results and has_scores and has_citations:
            print(f"✅ 5.3: Search with scoring successful ({len(search_results)} results)")
            print(f"   → Top result: {search_results[0].get('content', '')[:40]}...")
            print(f"   → Score: {search_results[0].get('relevance_score', 0):.2f}")
            print(f"   → Citation: {search_results[0].get('citation', '')}")
            results["passed"] += 1
        else:
            print(f"❌ 5.3: Search missing expected fields")
            results["failed"] += 1
    except Exception as e:
        print(f"❌ 5.3: Search error - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 5.4: Search by entity
    try:
        entity_results = search.search_by_entity("production")
        print(f"✅ 5.4: Search by entity ({len(entity_results)} results)")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 5.4: Entity search error - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # Test 5.5: Search by topic
    try:
        topic_results = search.search_by_topic("testing")
        print(f"✅ 5.5: Search by topic ({len(topic_results)} results)")
        results["passed"] += 1
    except Exception as e:
        print(f"❌ 5.5: Topic search error - {e}")
        results["failed"] += 1
    results["total"] += 1
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    score = (results["passed"] / results["total"] * 100) if results["total"] > 0 else 0
    
    print(f"Total: {results['total']}")
    print(f"Passed: {results['passed']}")
    print(f"Failed: {results['failed']}")
    print(f"Score: {score:.1f}%")
    
    if score >= 90:
        print("\n🎉 EXCELLENT - All features working!")
    elif score >= 70:
        print("\n👍 GOOD - Minor issues to fix")
    else:
        print("\n⚠️ NEEDS WORK - Review failures")
    
    return results


if __name__ == "__main__":
    results = run_tests()
