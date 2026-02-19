"""Captcha solving services."""
import os
import time
import base64
import requests
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlencode
import json


@dataclass
class CaptchaSolution:
    """Represents a captcha solution."""
    code: str
    provider: str
    task_id: Optional[str] = None


class CaptchaProvider(ABC):
    """Abstract base class for captcha providers."""
    
    @abstractmethod
    def solve_image(self, image_path: str = None, image_url: str = None) -> CaptchaSolution:
        """Solve image captcha."""
        pass
    
    @abstractmethod
    def solve_recaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        pass
    
    @abstractmethod
    def solve_hcaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve hCaptcha."""
        pass


class TwoCaptcha(CaptchaProvider):
    """2Captcha API integration."""
    
    BASE_URL = "https://2captcha.com"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TWOCAPTCHA_KEY")
        if not self.api_key:
            raise ValueError("2Captcha API key required. Set TWOCAPTCHA_KEY")
    
    def _request(self, method: str, params: Dict = None) -> Dict:
        """Make API request."""
        params = params or {}
        params["key"] = self.api_key
        params["json"] = 1
        
        url = f"{self.BASE_URL}/{method}.php"
        response = requests.get(url, params=params, timeout=30)
        return response.json()
    
    def _submit(self, method: str, params: Dict) -> str:
        """Submit captcha and get ID."""
        result = self._request(method, params)
        
        if result.get("status") == 1:
            return result["request"]
        
        raise Exception(f"Captcha submission failed: {result.get('request', 'Unknown error')}")
    
    def _wait_for_result(self, task_id: str, timeout: int = 120) -> str:
        """Poll for solution."""
        start = time.time()
        
        while time.time() - start < timeout:
            result = self._request("res", {"id": task_id})
            
            if result.get("status") == 1:
                return result["request"]
            
            if result.get("request") == "CAPCHA_NOT_READY":
                time.sleep(5)
                continue
            
            # Error
            if isinstance(result.get("request"), str) and "ERROR" in result["request"]:
                raise Exception(f"Captcha solve error: {result['request']}")
            
            time.sleep(5)
        
        raise Exception("Captcha solve timeout")
    
    def solve_image(self, image_path: str = None, image_url: str = None) -> CaptchaSolution:
        """Solve image captcha."""
        params = {}
        
        if image_path:
            with open(image_path, "rb") as f:
                files = {"file": f}
                response = requests.post(
                    f"{self.BASE_URL}/in.php",
                    data={"key": self.api_key, "json": 1},
                    files=files,
                    timeout=30
                )
            result = response.json()
            
            if result.get("status") != 1:
                raise Exception(f"Upload failed: {result.get('request')}")
            
            task_id = result["request"]
        
        elif image_url:
            params["body"] = image_url
            task_id = self._submit("load", params)
        
        else:
            raise ValueError("Either image_path or image_url required")
        
        # Wait for solution
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="2captcha",
            task_id=task_id
        )
    
    def solve_recaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        params = {
            "googlekey": sitekey,
            "pageurl": url,
            "method": "userrecaptcha"
        }
        
        task_id = self._submit("in", params)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="2captcha",
            task_id=task_id
        )
    
    def solve_hcaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve hCaptcha."""
        params = {
            "sitekey": sitekey,
            "pageurl": url,
            "method": "hcaptcha"
        }
        
        task_id = self._submit("in", params)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="2captcha",
            task_id=task_id
        )
    
    def solve_recaptcha_v3(self, sitekey: str, url: str, action: str = "verify", min_score: float = 0.3) -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        params = {
            "googlekey": sitekey,
            "pageurl": url,
            "version": "v3",
            "action": action,
            "min_score": min_score,
            "method": "userrecaptcha"
        }
        
        task_id = self._submit("in", params)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="2captcha",
            task_id=task_id
        )


class AntiCaptcha(CaptchaProvider):
    """Anti-Captcha API integration."""
    
    BASE_URL = "https://api.anti-captcha.com"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ANTICAPTCHA_KEY")
        if not self.api_key:
            raise ValueError("Anti-Captcha API key required. Set ANTICAPTCHA_KEY")
    
    def _request(self, method: str, data: Dict) -> Dict:
        """Make API request."""
        data["clientKey"] = self.api_key
        
        response = requests.post(
            f"{self.BASE_URL}/{method}",
            json=data,
            timeout=30
        )
        return response.json()
    
    def _submit(self, task_data: Dict) -> str:
        """Submit captcha and get ID."""
        result = self._request("createTask", {"task": task_data})
        
        if result.get("errorId") == 0:
            return result["taskId"]
        
        raise Exception(f"Submission failed: {result.get('errorDescription', 'Unknown')}")
    
    def _wait_for_result(self, task_id: str, timeout: int = 120) -> str:
        """Poll for solution."""
        start = time.time()
        
        while time.time() - start < timeout:
            result = self._request("getTaskResult", {"taskId": task_id})
            
            if result.get("status") == "ready":
                return result["solution"]["gRecaptchaResponse"]
            
            if result.get("status") == "processing":
                time.sleep(5)
                continue
            
            raise Exception(f"Solve error: {result}")
        
        raise Exception("Captcha solve timeout")
    
    def solve_image(self, image_path: str = None, image_url: str = None) -> CaptchaSolution:
        """Solve image captcha."""
        task_data = {"type": "ImageToTextTask"}
        
        if image_path:
            with open(image_path, "rb") as f:
                task_data["body"] = base64.b64encode(f.read()).decode()
        elif image_url:
            task_data["body"] = image_url.replace("data:", "").split(",", 1)[1] if "," in image_url else image_url
        else:
            raise ValueError("Either image_path or image_url required")
        
        task_id = self._submit(task_data)
        
        start = time.time()
        while time.time() - start < 120:
            result = self._request("getTaskResult", {"taskId": task_id})
            
            if result.get("status") == "ready":
                return CaptchaSolution(
                    code=result["solution"]["text"],
                    provider="anticaptcha",
                    task_id=task_id
                )
            
            time.sleep(5)
        
        raise Exception("Captcha solve timeout")
    
    def solve_recaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve reCAPTCHA v2."""
        task_data = {
            "type": "RecaptchaV2TaskProxyless",
            "websiteURL": url,
            "websiteKey": sitekey
        }
        
        task_id = self._submit(task_data)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="anticaptcha",
            task_id=task_id
        )
    
    def solve_hcaptcha(self, sitekey: str, url: str) -> CaptchaSolution:
        """Solve hCaptcha."""
        task_data = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": url,
            "websiteKey": sitekey
        }
        
        task_id = self._submit(task_data)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="anticaptcha",
            task_id=task_id
        )

    def solve_recaptcha_v3(self, sitekey: str, url: str, action: str = "verify", min_score: float = 0.3) -> CaptchaSolution:
        """Solve reCAPTCHA v3."""
        task_data = {
            "type": "RecaptchaV3TaskProxyless",
            "websiteURL": url,
            "websiteKey": sitekey,
            "minScore": min_score,
            "action": action
        }
        
        task_id = self._submit(task_data)
        code = self._wait_for_result(task_id)
        
        return CaptchaSolution(
            code=code,
            provider="anticaptcha",
            task_id=task_id
        )


class CaptchaSolver:
    """Unified captcha solver with multiple provider support."""
    
    PROVIDERS = {
        "2captcha": TwoCaptcha,
        "anticaptcha": AntiCaptcha,
    }
    
    def __init__(self, provider: str = "2captcha", api_key: str = None):
        """Initialize solver.
        
        Args:
            provider: "2captcha" or "anticaptcha"
            api_key: Provider API key (or use env var)
        """
        provider_class = self.PROVIDERS.get(provider)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(self.PROVIDERS.keys())}")
        
        self.provider = provider_class(api_key)
        self.provider_name = provider
    
    def solve_image(self, image_path: str = None, image_url: str = None) -> str:
        """Solve image captcha.
        
        Args:
            image_path: Path to image file
            image_url: URL of image
        
        Returns:
            Solution string
        """
        solution = self.provider.solve_image(image_path, image_url)
        return solution.code
    
    def solve_recaptcha(self, sitekey: str, url: str, version: str = "v2") -> str:
        """Solve reCAPTCHA.
        
        Args:
            sitekey: Site key from the page
            url: Page URL
            version: "v2" or "v3"
        
        Returns:
            gRecaptchaResponse token
        """
        if version == "v3":
            solution = self.provider.solve_recaptcha_v3(sitekey, url)
        else:
            solution = self.provider.solve_recaptcha(sitekey, url)
        
        return solution.code
    
    def solve_hcaptcha(self, sitekey: str, url: str) -> str:
        """Solve hCaptcha.
        
        Args:
            sitekey: Site key from the page
            url: Page URL
        
        Returns:
            hCaptcha response token
        """
        solution = self.provider.solve_hcaptcha(sitekey, url)
        return solution.code
    
    # Aliases
    def solve(self, captcha_type: str, **kwargs) -> str:
        """Generic solve method.
        
        Args:
            captcha_type: "image", "recaptcha", "hcaptcha"
            **kwargs: Type-specific arguments
        """
        if captcha_type == "image":
            return self.solve_image(**kwargs)
        elif captcha_type == "recaptcha":
            return self.solve_recaptcha(**kwargs)
        elif captcha_type == "hcaptcha":
            return self.solve_hcaptcha(**kwargs)
        else:
            raise ValueError(f"Unknown captcha type: {captcha_type}")


# Convenience function
def solve_captcha(captcha_type: str, provider: str = "2captcha", **kwargs) -> str:
    """Quick captcha solving.
    
    Args:
        captcha_type: "image", "recaptcha", "hcaptcha"
        provider: "2captcha" or "anticaptcha"
        **kwargs: Type-specific arguments
    
    Returns:
        Solution string
    """
    solver = CaptchaSolver(provider=provider)
    return solver.solve(captcha_type, **kwargs)
