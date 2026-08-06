import requests
import time
import webbrowser
import json
import base64
import uuid

CLIENT_ID = "13499bdf-784c-4123-a1d8-6b33a6c7004a"

def get_device_code():
    resp = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
        data={
            "client_id": CLIENT_ID,
            "scope": "XboxLive.signin offline_access"
        }
    )
    if resp.status_code != 200:
        print("获取设备码失败:", resp.text)
        return None
    return resp.json()

def poll_for_token(device_data):
    print("等待授权...（按 Ctrl+C 可取消）")
    while True:
        time.sleep(5)
        resp = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_data["device_code"]
            }
        )
        if resp.status_code == 200:
            print("成功获取 OAuth 令牌！")
            return resp.json()
        elif resp.status_code == 400:
            error = resp.json().get("error")
            if error == "authorization_pending":
                print(".", end="", flush=True)
                continue
            elif error == "slow_down":
                print("\n请求过频繁，等待 10 秒...")
                time.sleep(10)
                continue
            else:
                print("\n轮询错误:", resp.text)
                return None
        else:
            print("\n请求令牌失败:", resp.text)
            return None

def xbox_live_auth(access_token):
    url = "https://user.auth.xboxlive.com/user/authenticate"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={access_token}"
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT"
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        print("Xbox Live 认证失败:", resp.text)
        return None
    data = resp.json()
    return {
        "token": data["Token"],
        "user_hash": data["DisplayClaims"]["xui"][0]["uhs"]
    }

def xsts_auth(xbox_token):
    url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbox_token]
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT"
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        print("XSTS 认证失败:", resp.text)
        return None
    return resp.json()["Token"]

def minecraft_auth(xsts_token, user_hash):
    url = "https://api.minecraftservices.com/authentication/login_with_xbox"
    headers = {"Content-Type": "application/json"}
    payload = {
        "identityToken": f"XBL3.0 x={user_hash};{xsts_token}"
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        print("Minecraft 认证失败:", resp.text)
        if "403" in resp.text or "Forbidden" in resp.text:
            print("提示：你的应用可能未获得 Minecraft API 权限，请提交审核表单 https://aka.ms/mce-reviewappid")
        return None
    data = resp.json()
    access_token = data["access_token"]
    profile_resp = requests.get(
        "https://api.minecraftservices.com/minecraft/profile",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if profile_resp.status_code != 200:
        print("获取玩家信息失败:", profile_resp.text)
        return None
    profile = profile_resp.json()
    return {
        "access_token": access_token,
        "uuid": profile["id"],
        "name": profile["name"]
    }

def main():
    device_data = get_device_code()
    if not device_data:
        return
    print(f"\n请访问 {device_data['verification_uri']} 并输入代码: {device_data['user_code']}")
    webbrowser.open(device_data['verification_uri'])
    
    oauth_data = poll_for_token(device_data)
    if not oauth_data:
        return
    access_token = oauth_data["access_token"]
    
    xbox_result = xbox_live_auth(access_token)
    if not xbox_result:
        return
    xbox_token = xbox_result["token"]
    user_hash = xbox_result["user_hash"]
    
    xsts_token = xsts_auth(xbox_token)
    if not xsts_token:
        return
    
    minecraft_result = minecraft_auth(xsts_token, user_hash)
    if not minecraft_result:
        return
    
    print("\n登录成功！")
    print(f"   玩家名: {minecraft_result['name']}")
    print(f"   UUID:   {minecraft_result['uuid']}")
    print(f"   Access Token: {minecraft_result['access_token'][:20]}...")

if __name__ == "__main__":
    main()