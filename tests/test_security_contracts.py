from pathlib import Path


def test_env_ignored_and_no_obvious_embedded_keys():
    gi = Path('.gitignore').read_text()
    assert '.env' in gi
    forbidden = ['BRIGHTDATA_API_KEY="', 'COGNEE_API_KEY="', 'ALPACA_SECRET_KEY="']
    for path in list(Path('agent').rglob('*.py')) + list(Path('scripts').glob('*.py')):
        txt = path.read_text(encoding='utf-8')
        assert not any(x in txt for x in forbidden)
