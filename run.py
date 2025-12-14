import re
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from api import NeteaseAPI
from downloader import Downloader

# ================= 配置区 =================
ALL_LEVELS = [
    'jymaster', # 0. 超清母带
    'sky',      # 1. 沉浸环绕
    'jyeffect', # 2. 高清臻音
    'hires',    # 3. Hi-Res
    'lossless', # 4. 无损
    'exhigh',   # 5. 极高
    'standard'  # 6. 标准
]

QUALITY_MAP = {
    'jymaster': '超清母带 (Master)',
    'sky':      '沉浸环绕 (Sky)',
    'jyeffect': '高清臻音 (Supreme)',
    'hires':    'Hi-Res',
    'lossless': '无损品质 (FLAC)',
    'exhigh':   '极高音质 (MP3)',
    'standard': '标准音质 (MP3)'
}

# 全局策略变量
CURRENT_STRATEGY = []
# ========================================

def format_size(size_bytes):
    if size_bytes == 0: return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:3.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def print_progress(current, total, width=30):
    if total == 0: return
    percent = current / total
    bar_len = int(width * percent)
    bar = '█' * bar_len + '░' * (width - bar_len)
    sys.stdout.write(f"\r[下载中] [{bar}] {int(percent * 100)}% ")
    sys.stdout.flush()

def clean_filename(text):
    return re.sub(r'[\\/:*?"<>|]', '_', text).strip()

def identify_input(api, text):
    if 'playlist' in text: return 'playlist', re.search(r'id=(\d+)', text).group(1)
    if 'song' in text: return 'song', re.search(r'id=(\d+)', text).group(1)
    if 'id=' in text: return 'unknown', re.search(r'id=(\d+)', text).group(1)
    if text.isdigit():
        detail = api.get_song_detail(text)
        if detail and detail.get('songs'): return 'song', text
        pl = api.get_playlist_detail(text)
        if pl: return 'playlist', text
    return 'unknown', text

def parse_indexes(input_str, max_len):
    """解析序号范围，如 1-5, 8"""
    if input_str.lower() == 'all': return set(range(max_len))
    
    indexes = set()
    try:
        # 兼容中文逗号
        parts = input_str.replace('，', ',').split(',')
        for p in parts:
            p = p.strip()
            if not p: continue
            
            if '-' in p:
                start, end = map(int, p.split('-'))
                start = max(1, start)
                end = min(max_len, end)
                if start <= end:
                    for i in range(start, end + 1):
                        indexes.add(i - 1)
            else:
                idx = int(p)
                if 1 <= idx <= max_len:
                    indexes.add(idx - 1)
    except:
        pass
    return indexes

def manual_set_strategy():
    global CURRENT_STRATEGY
    print("-" * 60)
    print("请选择你的账号身份 (决定下载音质上限):")
    print("1. 黑胶 SVIP  [尝试: 母带 -> 臻音 -> 无损...]")
    print("2. 黑胶 VIP   [尝试: 臻音 -> HiRes -> 无损...]")
    print("3. 普通用户   [尝试: 极高(MP3) -> 标准...]")
    print("-" * 60)
    while True:
        choice = input("> 请输入序号 (1/2/3): ").strip()
        if choice == '1': CURRENT_STRATEGY = ALL_LEVELS; break
        elif choice == '2': CURRENT_STRATEGY = ALL_LEVELS[2:]; break
        elif choice == '3': CURRENT_STRATEGY = ALL_LEVELS[5:]; break

def scan_available_qualities(api, song_id):
    available_options = []
    seen_specs = set() 
    for level in CURRENT_STRATEGY:
        res = api.get_song_url(song_id, level)
        if not res or not res.get('data'): continue
        data = res['data'][0]
        url = data.get('url')
        size = data.get('size')
        actual_level = data.get('level')
        file_type = data.get('type', '').upper()
        if not url or size == 0: continue
        
        spec_key = (actual_level, size)
        if spec_key in seen_specs: continue
        seen_specs.add(spec_key)
        
        available_options.append({
            'req_level': level,
            'act_level': actual_level,
            'display': QUALITY_MAP.get(actual_level, actual_level),
            'size': size,
            'ext': file_type,
            'url': url
        })
    return available_options

def download_file_stream(downloader, url, path, metadata, total_size, quiet_mode=False):
    if os.path.exists(path):
        if not quiet_mode: print(f"[提示] 文件已存在: {os.path.basename(path)}")
        return "EXISTS"
    try:
        import requests
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            downloaded = 0
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if not quiet_mode: print_progress(downloaded, total_size)
        if not quiet_mode: print() 
        downloader.add_tags(path, metadata)
        return "SUCCESS"
    except Exception as e:
        return f"ERROR: {str(e)}"

def process_single_song(api, downloader, song_id, auto_best=False, quiet_mode=False):
    detail = api.get_song_detail(song_id)
    if not detail.get('songs'): return

    s = detail['songs'][0]
    name = s['name']
    artist = " & ".join([ar['name'] for ar in s['ar']])
    album = s['al']['name']
    
    if not quiet_mode:
        print("-" * 60)
        print(f"歌名 : {name} | 歌手 : {artist}")
        print("-" * 60)
        print("正在分析...", end='', flush=True)

    options = scan_available_qualities(api, song_id)
    if not quiet_mode: print(" 完成")

    if not options:
        msg = "[错误] 无法获取下载链接"
        if not quiet_mode: print(msg)
        else: print(f"[失败] {name} - {msg}")
        return

    selected_opt = None
    if auto_best:
        selected_opt = options[0]
    else:
        print(f"{'序号':<6} {'格式':<8} {'大小':<12} {'音质'}")
        print("-" * 60)
        for idx, opt in enumerate(options):
            print(f"{idx+1:<6} {opt['ext']:<8} {format_size(opt['size']):<12} {opt['display']}")
        print("-" * 60)
        while True:
            choice = input("序号 (默认1): ").strip()
            if not choice: selected_opt = options[0]; break
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                selected_opt = options[int(choice)-1]; break

    main_artist = clean_filename(s['ar'][0]['name'])
    safe_title = clean_filename(f"{artist} - {name}")
    ext = selected_opt['ext'].lower()
    save_dir = os.path.join("MyMusic", main_artist)
    if not os.path.exists(save_dir): os.makedirs(save_dir)
    file_path = os.path.join(save_dir, f"{safe_title}.{ext}")
    
    lrc_data = api.get_lyric(song_id)
    metadata = {
        'name': name, 'artist': artist, 'album': album,
        'pic_url': s['al']['picUrl'], 
        'lyric': lrc_data.get('lrc', {}).get('lyric', '')
    }
    
    if quiet_mode:
        print(f"[开始] {name} [{selected_opt['display']}]")
    else:
        print(f"[选中] {selected_opt['display']}")

    res = download_file_stream(downloader, selected_opt['url'], file_path, metadata, selected_opt['size'], quiet_mode)
    
    if quiet_mode:
        if res == "SUCCESS": print(f"[完成] {name}")
        elif res == "EXISTS": pass
        else: print(f"[错误] {name}: {res}")

def main():
    api = NeteaseAPI()
    downloader = Downloader("MyMusic")
    
    print("=" * 60)
    print("网易云音乐下载助手")
    print("特性: 歌单自选多线程")
    print("=" * 60)
    
    manual_set_strategy()
    print("-" * 60)

    while True:
        try:
            raw = input("\n> 请输入 歌曲ID / 歌单链接 (q退出): ").strip()
            if raw.lower() == 'q': break
            if not raw: continue
            
            type_str, real_id = identify_input(api, raw)
            
            if type_str == 'song':
                process_single_song(api, downloader, real_id)
            
            elif type_str == 'playlist':
                pl = api.get_playlist_detail(real_id)
                if not pl:
                    print("[错误] 无法获取歌单信息")
                    continue
                
                track_ids = pl['track_ids']
                print(f"[歌单] {pl['name']} (共 {len(track_ids)} 首)")
                print("1. 下载全部 (自动最高音质)")
                print("2. 自选歌曲")
                
                sel = input("> 请选择: ").strip()
                final_ids = []
                
                if sel == '1':
                    final_ids = track_ids
                elif sel == '2':
                    print(f"\n[列表] 正在获取 {len(track_ids)} 首歌曲详情...")
                    # 批量获取详情以便展示
                    all_songs_display = []
                    batch_size = 50
                    for i in range(0, len(track_ids), batch_size):
                        batch = track_ids[i:i+batch_size]
                        det = api.get_song_detail(batch)
                        if det and 'songs' in det:
                            all_songs_display.extend(det['songs'])
                    
                    print("-" * 60)
                    for idx, s in enumerate(all_songs_display):
                        ar_name = s['ar'][0]['name'] if s['ar'] else "未知"
                        print(f"{idx+1:03d}. {s['name'][:30]:<30} - {ar_name}")
                    print("-" * 60)
                    
                    print("[输入] 支持序号: 1, 3-5, 10 或 'all' (回车取消)")
                    sel_idx_str = input("> 请输入: ").strip()
                    
                    if not sel_idx_str: continue
                    
                    indexes = parse_indexes(sel_idx_str, len(track_ids))
                    if not indexes:
                        print("[提示] 未选择有效歌曲")
                        continue
                    
                    # 按照索引提取ID
                    final_ids = [track_ids[i] for i in sorted(list(indexes))]

                if final_ids:
                    print(f"\n[线程池] 启动 4 线程下载 {len(final_ids)} 首歌曲...")
                    print("-" * 40)
                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = []
                        for tid in final_ids:
                            futures.append(executor.submit(process_single_song, api, downloader, tid, True, True))
                        for _ in as_completed(futures): pass
                    print("-" * 40)
                    print(f"[完成] 任务结束")
            else:
                print("[警告] 无法识别")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[错误] {str(e)}")

if __name__ == "__main__":
    main()