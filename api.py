import json
import requests
import urllib.parse
from random import randrange
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import hashlib

class NeteaseAPI:
    def __init__(self, cookie_path="cookie.txt"):
        # 模拟最新 PC 客户端
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 NeteaseMusicDesktop/3.0.1.888',
            'Referer': 'https://music.163.com/',
        }
        self.cookies = self._load_cookie(cookie_path)
        self.aes_key = b"e82ckenh8dichen8"

    def _load_cookie(self, path):
        cookies = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                for item in content.split(';'):
                    if '=' in item:
                        k, v = item.strip().split('=', 1)
                        cookies[k] = v
        except FileNotFoundError:
            pass
        
        # 必要的伪装
        cookies.update({
            "os": "pc",
            "appver": "8.10.90",
            "osver": "Microsoft-Windows-10-Professional-build-19043-64bit",
            "deviceId": "pyncm-user"
        })
        return cookies

    def _encrypt(self, text):
        padder = padding.PKCS7(algorithms.AES(self.aes_key).block_size).padder()
        padded_data = padder.update(text.encode()) + padder.finalize()
        cipher = Cipher(algorithms.AES(self.aes_key), modes.ECB())
        encryptor = cipher.encryptor()
        return (encryptor.update(padded_data) + encryptor.finalize()).hex().upper()

    def _request(self, url, data):
        url_path = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
        data_json = json.dumps(data)
        digest = hashlib.md5(f"nobody{url_path}use{data_json}md5forencrypt".encode()).hexdigest()
        params = f"{url_path}-36cd479b6b5-{data_json}-36cd479b6b5-{digest}"
        enc_params = self._encrypt(params)
        
        try:
            resp = requests.post(url, headers=self.headers, cookies=self.cookies, data={"params": enc_params})
            return resp.json()
        except:
            return None

    def get_user_profile(self):
        """获取用户详情，用于判断 VIP 等级"""
        url = "https://interface3.music.163.com/eapi/v1/user/info"
        # 不需要复杂参数，只要 Cookie 对了就行
        return self._request(url, {})

    def get_song_url(self, song_id, level='lossless'):
        url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
        header = {
            "os": "pc",
            "appver": "8.10.90",
            "osver": "Microsoft-Windows-10-Professional-build-19043-64bit",
            "deviceId": "pyncm-user",
            "requestId": str(randrange(20000000, 30000000))
        }
        payload = {
            'ids': [int(song_id)],
            'level': level,
            'encodeType': 'flac',
            'header': json.dumps(header)
        }
        if level == 'sky': payload['immerseType'] = 'c51'
        return self._request(url, payload)

    def get_song_detail(self, song_ids):
        if not isinstance(song_ids, list): song_ids = [song_ids]
        c_list = [{"id": int(sid), "v": 0} for sid in song_ids]
        url = "https://interface3.music.163.com/api/v3/song/detail"
        data = {'c': json.dumps(c_list)}
        try:
            resp = requests.post(url, headers=self.headers, cookies=self.cookies, data=data)
            return resp.json()
        except: return {}

    def get_lyric(self, song_id):
        url = "https://interface3.music.163.com/api/song/lyric"
        data = {'id': song_id, 'cp': 'false', 'tv': '0', 'lv': '0', 'rv': '0', 'kv': '0', 'yv': '0', 'ytv': '0', 'yrv': '0'}
        try:
            resp = requests.post(url, headers=self.headers, cookies=self.cookies, data=data)
            return resp.json()
        except: return {}
        
    def get_playlist_detail(self, playlist_id):
        url = "https://music.163.com/api/v6/playlist/detail"
        data = {'id': playlist_id, 'n': 0, 's': 8} 
        try:
            resp = requests.post(url, headers=self.headers, cookies=self.cookies, data=data)
            res_json = resp.json()
            if not res_json.get('playlist'): return None
            playlist = res_json['playlist']
            track_ids = [t['id'] for t in playlist.get('trackIds', [])]
            return {'name': playlist['name'], 'cover': playlist['coverImgUrl'], 'track_ids': track_ids}
        except: return None