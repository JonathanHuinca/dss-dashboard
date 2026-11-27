import ipaddress
import re
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

PUERTOS_SMTP_PERMITIDOS = {25, 465, 587, 2525}
HOSTS_INTERNOS_PROHIBIDOS = {"localhost", "localhost.localdomain", "db", "uct-dss-db-1", "metadata", "metadata.google.internal"}

REDES_METADATA_Y_CERO = (
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("fe80::/10"),
)

REDES_PRIVADAS_Y_LOOPBACK = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def sanitizar_error_credencial(error: Any, secreto: Optional[str] = None) -> str:
    """Elimina cualquier secreto o token visible del texto de error antes de registrar o responder."""
    texto = str(error or "Error desconocido")
    if secreto and len(secreto.strip()) >= 4:
        texto = texto.replace(secreto.strip(), "[REDACTED]")
    texto = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\b(sk-[A-Za-z0-9_\-]{6,}|AIza[A-Za-z0-9_\-]{6,})", "[REDACTED]", texto)
    return texto


def _parsear_ip_literal(hostname: str) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    limpio = hostname.strip("[]")
    try:
        return ipaddress.ip_address(limpio)
    except ValueError:
        return None


def validar_url_proveedor_ia(url: str, permitir_local: bool = False) -> str:
    """Valida la URL base de un proveedor LLM bloqueando rutas SSRF y metadatos cloud."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("La URL base del proveedor no puede estar vacía.")

    parsed = urlparse(raw)
    if parsed.username or parsed.password:
        raise ValueError("La URL base no debe contener credenciales embebidas.")
    if not parsed.hostname:
        raise ValueError("La URL base debe incluir un nombre de host válido.")

    esquema = (parsed.scheme or "").lower()
    if not permitir_local and esquema != "https":
        raise ValueError("Los proveedores externos requieren esquema HTTPS obligatorio.")
    if permitir_local and esquema not in {"http", "https"}:
        raise ValueError("Solo se permiten esquemas HTTP o HTTPS.")

    host_lower = parsed.hostname.lower().rstrip(".")
    ip_obj = _parsear_ip_literal(host_lower)

    if ip_obj is not None:
        # Bloqueo absoluto de metadatos cloud y dirección nula incluso en modo local
        if any(ip_obj in red for red in REDES_METADATA_Y_CERO) or ip_obj.is_multicast:
            raise ValueError("Dirección IP restringida por seguridad anti-SSRF.")
        if not permitir_local and (
            ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved
            or any(ip_obj in red for red in REDES_PRIVADAS_Y_LOOPBACK)
        ):
            raise ValueError("Las URLs de proveedores externos no pueden apuntar a redes privadas o locales.")
    else:
        if host_lower in {"metadata", "metadata.google.internal"}:
            raise ValueError("Host de metadatos restringido por seguridad.")
        if not permitir_local and (host_lower in HOSTS_INTERNOS_PROHIBIDOS or host_lower.endswith(".local") or host_lower.endswith(".internal")):
            raise ValueError("Los proveedores externos no pueden apuntar a hosts internos o locales.")

    return raw.rstrip("/")


def validar_host_smtp(host: str, port: int) -> Tuple[str, int]:
    """Valida host y puerto SMTP permitiendo dominios e intranet UCT y bloqueando SSRF local/cloud."""
    host_limpio = (host or "").strip()
    if not host_limpio:
        raise ValueError("El servidor SMTP (host) no puede estar vacío.")
    if "://" in host_limpio or any(c.isspace() or ord(c) < 32 for c in host_limpio):
        raise ValueError("El host SMTP contiene caracteres inválidos o esquema URL.")

    if port not in PUERTOS_SMTP_PERMITIDOS:
        raise ValueError("Puerto SMTP no permitido. Use uno estándar: 25, 465, 587 o 2525.")

    host_lower = host_limpio.lower().rstrip(".")
    if host_lower in HOSTS_INTERNOS_PROHIBIDOS:
        raise ValueError("Host SMTP interno no permitido por seguridad.")

    ip_obj = _parsear_ip_literal(host_lower)
    if ip_obj is not None:
        if (
            any(ip_obj in red for red in REDES_METADATA_Y_CERO)
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            raise ValueError("Dirección IP SMTP restringida por seguridad anti-SSRF.")

    return host_limpio, port
