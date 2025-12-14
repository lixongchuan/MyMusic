import os
import requests
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, TRCK, USLT

class Downloader:
    def __init__(self, save_dir="downloads"):
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

    def download_file(self, url, filename):
        """下载文件流"""
        print(f"⬇️ 正在下载: {filename} ...")
        path = os.path.join(self.save_dir, filename)
        if os.path.exists(path):
            print("   文件已存在，跳过。")
            return path
        
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return path
        except Exception as e:
            print(f"❌ 下载失败: {e}")
            return None

    def add_tags(self, file_path, info):
        """写入元数据（封面、歌词、歌手等）"""
        if not file_path: return
        print("🏷️ 正在写入标签...")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        # 下载封面图片
        pic_data = None
        if info.get('pic_url'):
            try:
                pic_data = requests.get(info['pic_url']).content
            except:
                pass

        try:
            if ext == '.flac':
                audio = FLAC(file_path)
                audio['TITLE'] = info['name']
                audio['ARTIST'] = info['artist']
                audio['ALBUM'] = info['album']
                
                if pic_data:
                    pic = Picture()
                    pic.data = pic_data
                    pic.type = 3
                    pic.mime = "image/jpeg"
                    audio.add_picture(pic)
                    
                if info.get('lyric'):
                    audio['LYRICS'] = info['lyric']
                
                audio.save()

            elif ext == '.mp3':
                audio = MP3(file_path, ID3=ID3)
                try:
                    audio.add_tags()
                except:
                    pass
                
                audio.tags.add(TIT2(encoding=3, text=info['name']))
                audio.tags.add(TPE1(encoding=3, text=info['artist']))
                audio.tags.add(TALB(encoding=3, text=info['album']))
                
                if pic_data:
                    audio.tags.add(APIC(
                        encoding=3, mime='image/jpeg', type=3, desc='Cover', data=pic_data
                    ))
                
                if info.get('lyric'):
                     audio.tags.add(USLT(encoding=3, lang='chi', desc='', text=info['lyric']))

                audio.save()
            print("✅ 处理完成！")
            
        except Exception as e:
            print(f"⚠️ 标签写入部分失败: {e}")