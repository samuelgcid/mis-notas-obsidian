# Canal de clipping

Pipeline para convertir vídeos largos (podcasts, streams, entrevistas) en clips
verticales y subirlos a **YouTube Shorts, TikTok e Instagram Reels**. Concepto
y flujo de trabajo en [[Wiki/Conceptos/Canal de clipping]].

```
URL o archivo ──► preparar ──► transcripcion.txt ──► (Claude elige momentos) ──► clips.yaml
                                                                                    │
                       subidas.json ◄── subir (YT / TikTok / IG) ◄── clips/*.mp4 ◄── cortar
```

> [!warning] Copyright: léelo antes de subir nada
> Recortar vídeos de otros sin permiso lleva a reclamaciones de Content ID,
> *strikes* y cierre del canal (3 strikes en YouTube = canal eliminado), y no
> se puede monetizar. Trabaja **solo con creadores que lo permitan**: programas
> de clipping oficiales (muchos streamers y podcasts los tienen, a veces
> pagados por visualizaciones, p. ej. vía Whop o Discord), o permiso por
> escrito. Por eso `clips.yaml` exige un campo `credito` y la subida falla
> sin él. Por defecto todo se sube en **privado** para que lo revises.

## Uso

```bash
pip install -r requirements.txt          # requiere ffmpeg instalado
cp config.example.yaml config.yaml

python -m clipper preparar "https://youtube.com/watch?v=..."   # o una ruta local
#   → trabajo/<id>/original.mp4, info.json, transcripcion.txt
#   Claude lee la transcripción y escribe trabajo/<id>/clips.yaml (ver clips.example.yaml)
python -m clipper cortar trabajo/<id>/clips.yaml               # → trabajo/<id>/clips/*.mp4
python -m clipper subir  trabajo/<id>/clips.yaml --plataformas youtube,tiktok,instagram
```

- `subir` apunta lo subido en `trabajo/<id>/subidas.json`; si lo repites no
  duplica clips.
- `--privacidad public` para publicar directamente (Instagram la exige: no
  tiene modo privado).
- Modos de encuadre por clip: `recorte` (franja 9:16, mueve `centro_x` para
  seguir a quien habla) o `desenfoque` (plano completo sobre fondo
  desenfocado, mejor para dos personas en plano).

## Cuando me mandas un vídeo

1. Ejecuto `preparar` con el enlace o archivo.
2. Leo la transcripción y propongo 3–8 momentos (30–60 s, con gancho en los
   primeros 2 s, que se entiendan sin contexto) con título y hashtags en
   `clips.yaml`. Te los enseño antes de cortar.
3. `cortar` y te paso los clips para que los veas.
4. Con tu OK, `subir` (en privado por defecto) y te doy los enlaces.

## Configurar cada plataforma (una vez)

Las cuentas/canales los creas tú; el pipeline solo necesita credenciales.

### YouTube (API oficial, la más sencilla)
1. Crea el canal en YouTube.
2. En [Google Cloud Console](https://console.cloud.google.com/): proyecto
   nuevo → habilita **YouTube Data API v3** → pantalla de consentimiento OAuth
   (tipo *External*, añádete como usuario de prueba) → credencial **OAuth
   client ID** de tipo *Desktop app* → descarga el JSON a
   `secretos/youtube_client_secret.json`.
3. `python -m clipper auth youtube` (abre el navegador, eliges el canal).
4. Cuota por defecto: 10.000 unidades/día ≈ **6 subidas al día**. Los vídeos
   subidos por apps no verificadas por Google pueden quedar bloqueados en
   privado hasta pasar la auditoría de la API.

### TikTok
1. App en [developers.tiktok.com](https://developers.tiktok.com/) con el
   producto **Content Posting API** y el scope `video.publish`.
2. Obtén un access token de usuario (OAuth de TikTok) y expórtalo como
   `TIKTOK_ACCESS_TOKEN`.
3. Hasta que TikTok audite la app, solo se publica en privado (`SELF_ONLY`).

### Instagram Reels
1. Cuenta de Instagram **profesional** vinculada a una página de Facebook.
2. App en [developers.facebook.com](https://developers.facebook.com/) con
   `instagram_content_publish` → token de larga duración en
   `INSTAGRAM_ACCESS_TOKEN` y el ID de la cuenta en `config.yaml`.
3. Límite: 50 publicaciones por API cada 24 h.

## Tests

```bash
pip install -r requirements-dev.txt && python -m pytest -q tests
```

Cubren el corte y el paso a 9:16 (ambos modos) con vídeos sintéticos, el
límite de duración y los textos con crédito obligatorio. Las subidas no tienen
tests: necesitan cuentas reales.
