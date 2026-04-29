#!/usr/bin/env python3
"""修复 websocket.py 的 stop_listening 逻辑"""
import re

path = '/Users/Zhuanz1/Desktop/code/helper/backend/app/api/websocket.py'
content = open(path).read()

# 找到 stop_listening 块并修复
# 原来：立即清空 session
# 修复：只设置 is_listening=False，不清空
old_pattern = r'(elif msg_type == "stop_listening":\s+session\.is_listening = False\s+)asr_service\.clear_session\(session_id\)\s+_session_last_full_text\.pop\(session_id, None\)\s+_session_transcript_count\.pop\(session_id, None\)\s+'

replacement = r'\1# 不立即清空 session，让队列中剩余的块处理完毕\n                # 只在 start_listening 时重置，避免停止后推送全量文本\n                '

new_content, count = re.subn(old_pattern, replacement, content)
if count > 0:
    open(path, 'w').write(new_content)
    print(f"✅ 修复成功，替换了 {count} 处")
else:
    print("❌ 未找到目标代码，打印 stop_listening 附近内容：")
    idx = content.find('stop_listening')
    while idx != -1:
        print(f"--- 位置 {idx} ---")
        print(repr(content[idx:idx+400]))
        idx = content.find('stop_listening', idx+1)
