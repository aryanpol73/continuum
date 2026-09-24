"""
PWA Setup and Injection Module for Continuum.
Provides installability as a Progressive Web App across Desktop, Android, and iOS.
"""

from __future__ import annotations
import os
import shutil
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import streamlit.file_util as file_util

PWA_TAGS = """    <!-- Continuum PWA Metadata -->
    <link rel="manifest" href="/app/static/manifest.json" />
    <meta name="theme-color" content="#0F766E" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="default" />
    <meta name="apple-mobile-web-app-title" content="Continuum" />
    <link rel="apple-touch-icon" href="/app/static/apple-touch-icon.png" />
    <link rel="apple-touch-icon" sizes="192x192" href="/app/static/icon-192.png" />
    <link rel="apple-touch-icon" sizes="512x512" href="/app/static/icon-512.png" />
    <script>
      if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
          navigator.serviceWorker.register('/app/static/sw.js')
            .then(function(reg) {
              console.log('[Continuum PWA] Service Worker registered with scope:', reg.scope);
            })
            .catch(function(err) {
              console.warn('[Continuum PWA] Service Worker registration failed:', err);
            });
        });
      }
    </script>
"""


def setup_pwa() -> None:
    """
    Ensures PWA assets are deployed into Streamlit's static serving folder
    and that index.html contains the necessary PWA manifest and service worker hooks.
    """
    base_dir = Path(__file__).resolve().parent.parent.parent
    app_static = base_dir / "app" / "static"

    try:
        st_static_dir = Path(file_util.get_static_dir())
        if st_static_dir.exists():
            # Copy static files to streamlit static dir
            for fname in [
                "manifest.json",
                "sw.js",
                "offline.html",
                "icon-192.png",
                "icon-512.png",
                "apple-touch-icon.png",
                "favicon-32x32.png",
            ]:
                src = app_static / fname
                if src.exists():
                    dst = st_static_dir / fname
                    shutil.copy2(src, dst)

            # Update favicon.png with the new icon
            fav_src = app_static / "icon-192.png"
            if fav_src.exists():
                shutil.copy2(fav_src, st_static_dir / "favicon.png")

            # Patch index.html if not already patched
            index_file = st_static_dir / "index.html"
            if index_file.exists():
                txt = index_file.read_text(encoding="utf-8")
                if "<!-- Continuum PWA Metadata -->" not in txt:
                    new_txt = txt.replace("<head>", "<head>\n" + PWA_TAGS, 1)
                    # Also replace default Streamlit title
                    new_txt = new_txt.replace("<title>Streamlit</title>", "<title>Continuum</title>")
                    index_file.write_text(new_txt, encoding="utf-8")
    except Exception as e:
        # Non-fatal if running in restricted environments
        pass


def inject_pwa_client_bridge() -> None:
    """
    DOM-level injection bridge to guarantee manifest and service worker registration
    even when running inside client-side SPAs or iframes.
    """
    bridge_js = """
    <script>
    (function() {
        try {
            const doc = (window.parent && window.parent.document) ? window.parent.document : document;
            const nav = (window.parent && window.parent.navigator) ? window.parent.navigator : navigator;
            const head = doc.head;

            // 1. Ensure manifest link exists and points to /app/static/manifest.json
            let link = doc.querySelector('link[rel="manifest"]');
            if (!link) {
                link = doc.createElement('link');
                link.rel = 'manifest';
                head.appendChild(link);
            }
            link.href = '/app/static/manifest.json';

            // 2. Ensure theme color
            let metaTheme = doc.querySelector('meta[name="theme-color"]');
            if (!metaTheme) {
                metaTheme = doc.createElement('meta');
                metaTheme.name = 'theme-color';
                head.appendChild(metaTheme);
            }
            metaTheme.content = '#0F766E';

            // 3. Apple mobile web app capable
            let metaApple = doc.querySelector('meta[name="apple-mobile-web-app-capable"]');
            if (!metaApple) {
                metaApple = doc.createElement('meta');
                metaApple.name = 'apple-mobile-web-app-capable';
                head.appendChild(metaApple);
            }
            metaApple.content = 'yes';

            // 4. Apple touch icon
            let touchIcon = doc.querySelector('link[rel="apple-touch-icon"]');
            if (!touchIcon) {
                touchIcon = doc.createElement('link');
                touchIcon.rel = 'apple-touch-icon';
                head.appendChild(touchIcon);
            }
            touchIcon.href = '/app/static/icon-192.png';

            // 5. Register Service Worker on navigator
            if ('serviceWorker' in nav) {
                nav.serviceWorker.register('/app/static/sw.js')
                    .then(function(reg) {
                        console.log('[Continuum PWA Client] Registered:', reg.scope);
                    })
                    .catch(function(err) {
                        console.warn('[Continuum PWA Client] Registration error:', err);
                    });
            }
        } catch (e) {
            console.error('[Continuum PWA Bridge Error]:', e);
        }
    })();
    </script>
    """
    if hasattr(st, "html"):
        st.html(bridge_js)
    else:
        components.html(bridge_js, height=0, width=0)


def render_pwa_sidebar_badge() -> None:
    """
    Renders an install information widget in the sidebar for mobile and desktop users.
    """
    with st.sidebar.expander("📱 Install App (PWA)", expanded=False):
        st.markdown(
            """
            **Continuum is installable on any device:**
            
            - **Desktop (Chrome / Edge / Brave):**
              Click the **Install** icon (⊕ / 📥) on the right side of your address bar.
            
            - **Android (Chrome):**
              Tap menu **⋮** &rarr; **Install app** or **Add to Home screen**.
            
            - **iPhone & iPad (Safari):**
              Tap **Share** (⎙) &rarr; scroll down &rarr; tap **Add to Home Screen**.
            
            *Runs standalone fullscreen with native app icon, fast caching, and offline support.*
            """
        )
