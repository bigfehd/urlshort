"""Utility functions for URL shortening."""
import base64
from typing import Optional


class Base62Encoder:
    """Base62 encoding/decoding for short codes.
    
    Uses alphabetical characters (a-z, A-Z) and digits (0-9)
    to create URL-friendly short codes.
    """

    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    BASE = len(ALPHABET)

    @classmethod
    def encode(cls, num: int) -> str:
        """Encode a number to Base62 string.
        
        Args:
            num: The number to encode
            
        Returns:
            Base62 encoded string
        """
        if num == 0:
            return cls.ALPHABET[0]

        encoded = ""
        while num > 0:
            encoded = cls.ALPHABET[num % cls.BASE] + encoded
            num //= cls.BASE

        return encoded

    @classmethod
    def decode(cls, encoded: str) -> int:
        """Decode a Base62 string to a number.
        
        Args:
            encoded: The Base62 string to decode
            
        Returns:
            Decoded integer
            
        Raises:
            ValueError: If the string contains invalid Base62 characters
        """
        num = 0
        for char in encoded:
            if char not in cls.ALPHABET:
                raise ValueError(f"Invalid Base62 character: {char}")
            num = num * cls.BASE + cls.ALPHABET.index(char)

        return num


def generate_short_code(db_id: int) -> str:
    """Generate a short code from database primary key.
    
    Args:
        db_id: The primary key from database
        
    Returns:
        Base62 encoded short code
    """
    return Base62Encoder.encode(db_id)


def validate_url(url: str) -> bool:
    """Validate URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid, False otherwise
    """
    return url.startswith(("http://", "https://")) and len(url) > 0


def get_client_ip(headers: dict) -> Optional[str]:
    """Extract client IP from request headers.
    
    Handles X-Forwarded-For header for deployments behind proxies.
    
    Args:
        headers: HTTP request headers
        
    Returns:
        Client IP address or None
    """
    forwarded_for = headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    return headers.get("x-real-ip", headers.get("client-host"))


class UserAgentParser:
    """Parse user agent string to detect device type."""

    MOBILE_KEYWORDS = [
        "mobile",
        "android",
        "iphone",
        "ipod",
        "windows phone",
        "blackberry",
        "samsung",
        "nokia",
        "htc",
        "nexus",
        "pixel",
    ]

    BOT_KEYWORDS = [
        "bot",
        "crawler",
        "spider",
        "scraper",
        "curl",
        "wget",
        "python",
        "httpclient",
        "php",
        "java",
        "googlebot",
        "bingbot",
        "slurp",
        "duckduckbot",
        "baiduspider",
        "yandexbot",
        "facebookexternalhit",
        "twitterbot",
        "linkedinbot",
        "whatsapp",
        "telegram",
        "viber",
    ]

    @classmethod
    def detect_device_type(cls, user_agent: Optional[str]) -> str:
        """Detect device type from user agent string.
        
        Args:
            user_agent: HTTP User-Agent header value
            
        Returns:
            One of: "mobile", "desktop", or "bot"
        """
        if not user_agent:
            return "desktop"

        user_agent_lower = user_agent.lower()

        # Check for bot first (higher priority)
        for bot_keyword in cls.BOT_KEYWORDS:
            if bot_keyword in user_agent_lower:
                return "bot"

        # Check for mobile
        for mobile_keyword in cls.MOBILE_KEYWORDS:
            if mobile_keyword in user_agent_lower:
                return "mobile"

        # Default to desktop
        return "desktop"
