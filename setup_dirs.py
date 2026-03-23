import os

base = r'c:\Users\admin\Documents\new_clone\ivr_bot.worktrees\copilot-worktree-2026-03-16T12-41-19\ecommerce_bot'
dirs = [
    r'backend\api',
    r'backend\agents',
    r'backend\database',
    r'backend\services',
    r'backend\voice',
    r'backend\logging',
    r'frontend\components\voice-ui',
    r'frontend\components\chat-timeline',
]
for d in dirs:
    path = os.path.join(base, d)
    os.makedirs(path, exist_ok=True)
    print(f'Created: {path}')

print('All directories created')
