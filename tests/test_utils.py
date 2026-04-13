"""Tests for utility functions."""
import pytest

from app.utils import Base62Encoder, generate_short_code, validate_url


class TestBase62Encoder:
    """Tests for Base62 encoding/decoding."""

    def test_encode_zero(self):
        """Test encoding zero."""
        assert Base62Encoder.encode(0) == "0"

    def test_encode_single_digit(self):
        """Test encoding single digit numbers."""
        assert Base62Encoder.encode(1) == "1"
        assert Base62Encoder.encode(9) == "9"
        assert Base62Encoder.encode(10) == "A"
        assert Base62Encoder.encode(35) == "Z"
        assert Base62Encoder.encode(36) == "a"

    def test_encode_large_number(self):
        """Test encoding large numbers."""
        encoded = Base62Encoder.encode(12345)
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_decode_single_character(self):
        """Test decoding single characters."""
        assert Base62Encoder.decode("0") == 0
        assert Base62Encoder.decode("1") == 1
        assert Base62Encoder.decode("A") == 10

    def test_decode_multi_character(self):
        """Test decoding multi-character strings."""
        encoded = Base62Encoder.encode(12345)
        decoded = Base62Encoder.decode(encoded)
        assert decoded == 12345

    def test_encode_decode_roundtrip(self):
        """Test encode/decode roundtrip."""
        test_numbers = [0, 1, 10, 100, 1000, 10000, 100000]
        for num in test_numbers:
            encoded = Base62Encoder.encode(num)
            decoded = Base62Encoder.decode(encoded)
            assert decoded == num

    def test_decode_invalid_character(self):
        """Test decoding with invalid characters."""
        with pytest.raises(ValueError):
            Base62Encoder.decode("!")


class TestGenerateShortCode:
    """Tests for short code generation."""

    def test_generate_short_code(self):
        """Test generating short codes from IDs."""
        code1 = generate_short_code(1)
        code2 = generate_short_code(2)
        code100 = generate_short_code(100)

        assert isinstance(code1, str)
        assert isinstance(code2, str)
        assert isinstance(code100, str)
        assert code1 != code2
        assert code2 != code100

    def test_generate_short_code_is_unique(self):
        """Test that different IDs generate different codes."""
        codes = [generate_short_code(i) for i in range(100)]
        assert len(codes) == len(set(codes))


class TestValidateURL:
    """Tests for URL validation."""

    def test_valid_http_url(self):
        """Test valid HTTP URLs."""
        assert validate_url("http://example.com")
        assert validate_url("http://example.com/path")
        assert validate_url("http://example.com/path?query=param")

    def test_valid_https_url(self):
        """Test valid HTTPS URLs."""
        assert validate_url("https://example.com")
        assert validate_url("https://example.com/path")
        assert validate_url("https://example.com/path?query=param")

    def test_invalid_url_no_protocol(self):
        """Test invalid URLs without protocol."""
        assert not validate_url("example.com")
        assert not validate_url("www.example.com")

    def test_invalid_url_wrong_protocol(self):
        """Test invalid URLs with wrong protocol."""
        assert not validate_url("ftp://example.com")
        assert not validate_url("file:///path/to/file")

    def test_empty_url(self):
        """Test empty URL."""
        assert not validate_url("")

    def test_long_url(self):
        """Test very long URL."""
        long_url = "https://example.com/" + "a" * 2000
        assert validate_url(long_url)
