import ai_services
import poster_engine

def test_constants_exist():
    assert '추천 · GPT Image 2.5 Sunburst' in ai_services.IMAGE_MODELS
    assert '빠른 초안' in ai_services.DESIGN_MODES
    assert '균형형' in ai_services.QUALITY_PRESETS
    assert 'editorial' in poster_engine.STYLE_LABELS
