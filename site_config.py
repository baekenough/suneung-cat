"""Labels and filters shared by the public and local leaderboards."""

SERVICE_NAME = '수능냥이'
TITLE = '2027학년도 수능 풀이 모델 리더보드'
SHORT_COURSES = {'화법과 작문': '화작', '언어와 매체': '언매'}
PROVIDERS = {'all': '전체', 'openai': 'OpenAI', 'anthropic': 'Anthropic',
             'gemini': 'Gemini', 'openrouter': 'OpenRouter', 'upstage': 'Upstage'}
PROVIDER_HOSTS = {'api.openai.com': 'openai', 'api.anthropic.com': 'anthropic',
                  'openrouter.ai': 'openrouter', 'api.upstage.ai': 'upstage'}
FRONTIER_MODELS = {'gpt-6.2-astra', 'gpt-6.2-sol', 'claude-fable-5-2', 'claude-opus-5-5',
                   'google/gemini-4-neon', 'google/gemini-4-hydrogen', 'google/gemini-4-carbon'}
