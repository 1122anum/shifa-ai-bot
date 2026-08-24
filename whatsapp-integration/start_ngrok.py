"""
start_ngrok.py — ngrok tunnel starter.

Usage:
    python start_ngrok.py

Tunnel tab tak chal ta rahega jab tak Ctrl+C na dabao.
"""

from pyngrok import ngrok, conf, process
import re, os, time

AUTH_TOKEN = "3IKWN1W8LKw7cKzN9UkgkidutVd_32zAAvdxbYFAHesu8A9EG"
PORT = 5000

def update_env(url):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    content = open(env_path).read()
    if "NGROK_PUBLIC_URL=" in content:
        content = re.sub(r"NGROK_PUBLIC_URL=.*", f"NGROK_PUBLIC_URL={url}", content)
    else:
        content += f"\nNGROK_PUBLIC_URL={url}\n"
    open(env_path, "w").write(content)

def main():
    print("=" * 55)
    print("   Shifa AI — ngrok Tunnel")
    print("=" * 55)

    # Kill any old processes
    try:
        process._current_processes.clear()
        ngrok.kill()
    except Exception:
        pass

    # Set token
    conf.get_default().auth_token = AUTH_TOKEN

    try:
        tunnel = ngrok.connect(PORT, "http", pooling_enabled=True)
        url = tunnel.public_url.replace("http://", "https://")

        print(f"\n  Tunnel LIVE!")
        print(f"\n  Public URL : {url}")
        print(f"  Webhook    : {url}/webhook/whatsapp")
        print(f"  Health     : {url}/health")
        print("\n" + "=" * 55)
        print(f"  Meta Console mein ye daalo:")
        print(f"  Callback URL : {url}/webhook/whatsapp")
        print(f"  Verify Token : shifa_verify_token")
        print("=" * 55)

        update_env(url)
        print(f"\n  .env updated!")
        print(f"  Tunnel chal raha hai... Ctrl+C se band karo\n")

        # Keep alive loop
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n  Tunnel band ho gaya.")
        ngrok.kill()
    except Exception as e:
        print(f"\n  Error: {e}")

if __name__ == "__main__":
    main()
