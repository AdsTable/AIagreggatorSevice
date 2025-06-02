# ai_client.py
import os
import yaml
import openai
import requests

class AIClient:
    def __init__(self, config_path: str = "ai_integrations.yaml"):
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        # Expand env vars in config (e.g., ${OPENAI_API_KEY})
        for provider, settings in cfg.items():
            for key, value in settings.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    cfg[provider][key] = os.getenv(env_key)
        self.config = cfg

    def ask_openai(self, prompt: str) -> str:
        api_key = self.config["openai"]["api_key"]
        model = self.config["openai"]["model"]
        openai.api_key = api_key
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    def ask_yandexgpt(self, prompt: str) -> str:
        api_key = self.config["yandexgpt"]["api_key"]
        endpoint = self.config["yandexgpt"]["endpoint"]
        model = self.config["yandexgpt"]["model"]
        headers = {"Authorization": f"Api-Key {api_key}"}
        data = {"modelUri": model, "completionOptions": {"stream": False}, "messages": [{"role": "user", "text": prompt}]}
        r = requests.post(endpoint, json=data, headers=headers)
        r.raise_for_status()
        return r.json()["result"]["alternatives"][0]["message"]["text"]

    def ask(self, prompt: str, provider: str = "openai") -> str:
        if provider == "openai":
            return self.ask_openai(prompt)
        elif provider == "yandexgpt":
            return self.ask_yandexgpt(prompt)
        else:
            raise ValueError(f"Unknown AI provider: {provider}")