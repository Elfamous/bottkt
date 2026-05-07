"""
Bot de vote automatique - Tous les sites combinés
================================================
Logiciel de vote autonome pour Serenity-Craft sur:
- serveur-prive.net (MTCaptcha via Mistral Pixtral)
- serveur-minecraft-vote.fr
- serveur-minecraft.com (reCAPTCHA via Mistral Pixtral)
"""

import asyncio
from playwright.async_api import async_playwright
import time
import logging
import sys
import requests
import json
import base64
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def random_mouse_move(page):
    """Effectue des mouvements de souris aléatoires pour paraître plus humain."""
    try:
        viewport = page.viewport_size
        x = random.randint(100, viewport['width'] - 100)
        y = random.randint(100, viewport['height'] - 100)
        await page.mouse.move(x, y)
        await page.wait_for_timeout(random.randint(100, 300))
    except:
        pass

ACCOUNTS = [
    {"username": "AlexCaill", "proxy": None}
]
MISTRAL_API_KEY = "P5bTDPAhdn9g8Q2QdEvCXH5VWeGViQh2"

def solve_mtcaptcha_with_mistral(b64_image):
    """Appelle directement l'API Vision de Mistral pour lire le captcha."""
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }
    
    # Préfixe requis pour Pixtral
    if not b64_image.startswith('data:image'):
        b64_image = f"data:image/png;base64,{b64_image}"
        
    prompt = "This is a captcha image. Read the characters (letters/numbers). Reply ONLY with the characters found. NO punctuation, NO spaces."
    
    data = {
        "model": "pixtral-12b-2409",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": b64_image}
                ]
            }
        ],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        result = response.json()
        if 'choices' in result:
            content = result['choices'][0]['message']['content'].strip()
            # Nettoyage au cas où l'IA bavarde
            content = ''.join(e for e in content if e.isalnum())
            return content
    except Exception as e:
        logging.error(f"Erreur API Mistral : {e}")
    return None

def solve_grid(b64_image, instruction):
    """Appel à Mistral Pixtral pour identifier les cases à cliquer (reCAPTCHA)."""
    url = "https://api.mistral.ai/v1/chat/completions"
    
    prompt = (
        f"Instruction: {instruction}. "
        "The image is a 3x3 grid of a reCAPTCHA challenge. "
        "Identify the numbers of the tiles where the requested object is present. "
        "Grid numbering: 1 2 3 (top), 4 5 6 (middle), 7 8 9 (bottom). "
        "Return ONLY a comma-separated list of numbers (e.g., 1,4,7). If none, return 'None'."
    )
    
    payload = {
        "model": "pixtral-12b-2409",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64_image}"}
                ]
            }
        ],
        "temperature": 0
    }
    
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        res_json = response.json()
        if 'choices' in res_json:
            content = res_json['choices'][0]['message']['content'].strip()
            logging.info(f"🧠 IA Response: {content}")
            if content.lower() == "none": return []
            return [int(x.strip()) for x in content.replace(" ", "").split(",") if x.strip().isdigit()]
        else:
            logging.error(f"❌ Mistral API Error: {res_json}")
            return []
    except Exception as e:
        logging.error(f"❌ Error calling Mistral: {e}")
        return []

async def vote_serveur_prive(username, proxy_conf=None):
    portal_url = "https://serenity-craft.fr/vote"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-webrtc',
                '--disable-webgl',
                '--disable-features=VizDisplayCompositor',
                '--disable-dev-shm-usage',
                '--no-zygote'
            ]
        )
        ctx_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
            "locale": "fr-FR",
            "timezone_id": "Europe/Paris",
            "permissions": ["geolocation"],
            "geolocation": {"latitude": 48.8566, "longitude": 2.3522},  # Paris coordinates
            "ignore_https_errors": True
        }
        if proxy_conf:
            ctx_args["proxy"] = proxy_conf
            logging.info(f"Proxy configuré: {proxy_conf['server']}")
            
        context = await browser.new_context(**ctx_args)
        
        # --- ROUTE INTERCEPTEUR AGRESSIF (ÉCONOMIE BANDE PASSANTE) ---
        async def route_interceptor(route):
            res_type = route.request.resource_type
            url = route.request.url.lower()
            
            # Laisser passer SEULEMENT l'essentiel pour le vote
            if "captcha" in url or "mtcaptcha" in url or "google" in url or "gstatic" in url:
                await route.continue_()
                return
            
            # Laisser passer les API et les formulaires
            if res_type in ["xhr", "fetch", "websocket"]:
                await route.continue_()
                return
            
            # BLOQUER TOUT le reste pour économiser la bande passante
            if res_type in ["image", "stylesheet", "font", "media", "other"]:
                await route.abort()
                return
                
            await route.continue_()

        await context.route("**/*", route_interceptor)
        # ----------------------------------
        
        page = await context.new_page()
        
        # Injecter JavaScript pour désactiver WebRTC et améliorer la détection
        await page.add_init_script("""
            // Désactiver WebRTC
            Object.defineProperty(navigator, 'webkitGetUserMedia', { get: () => undefined });
            Object.defineProperty(navigator, 'mozGetUserMedia', { get: () => undefined });
            Object.defineProperty(navigator, 'getUserMedia', { get: () => undefined });
            
            // Masquer les propriétés d'automation
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr', 'en'] });
            
            // Override Chrome object
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
        """)
        
        try:
            logging.info(f"Navigation vers le portail {portal_url}")
            await page.goto(portal_url, wait_until='networkidle')
            await page.wait_for_timeout(2000)
            await random_mouse_move(page)
            
            # --- 1. Fermeture du popup Bedrock si présent ---
            try:
                # Le popup peut prendre un moment à apparaître
                close_btn = await page.query_selector(".btn-close")
                if close_btn and await close_btn.is_visible():
                    await close_btn.click()
                    logging.info("Popup informatif fermé.")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logging.debug(f"Pas de popup à fermer ou erreur : {e}")

            # --- 2. Remplissage du Pseudo sur le portail ---
            pseudo_portal = await page.wait_for_selector("input#stepNameInput", timeout=15000)
            if pseudo_portal:
                await pseudo_portal.click()
                await pseudo_portal.fill(username)
                await page.wait_for_timeout(500)  # Délai réaliste
                await random_mouse_move(page)
                await page.click("button[type='submit']")
                logging.info(f"Pseudo '{username}' saisi sur le portail.")
                await page.wait_for_timeout(3000)  # Attendre la validation
            
            # --- 2. Clic sur serveur-prive.net ---
            logging.info("Recherche du lien serveur-prive.net...")
            
            portal_link = await page.wait_for_selector('a[href*="serveur-prive.net"]', timeout=10000)
            link_class = await portal_link.get_attribute("class")
            if link_class and "disabled" in link_class:
                logging.info(f"⏳ Le vote pour {username} est en cooldown (bouton désactivé). Annulation du cycle.")
                return
                
            async with page.expect_popup() as popup_info:
                await portal_link.click()
            
            page = await popup_info.value # On bascule sur le nouvel onglet
            await page.wait_for_load_state('networkidle')
            logging.info("Nouvel onglet serveur-prive.net ouvert.")
            # Attendre moins longtemps avec le proxy pour économiser la bande passante
            wait_time = 2000 if proxy_conf else 2000
            await page.wait_for_timeout(wait_time)  # Attendre que la page soit complètement chargée
            
            # --- 3. Clic sur le bouton 'Voter' initial de serveur-prive ---
            logging.info("Recherche du bouton 'Voter' initial...")
            # On utilise plusieurs sélecteurs au cas où le site change (bouton ou lien)
            vote_btn_selectors = "#voteBtn, a.btn-vote, button:has-text('Voter'), a:has-text('Voter')"
            
            try:
                vote_now_btn = await page.wait_for_selector(vote_btn_selectors, timeout=10000)
                if vote_now_btn:
                    logging.info("Clic sur le bouton 'Voter' vers la page de vote...")
                    await vote_now_btn.click()
                    # On attend le chargement de la nouvelle page de vote
                    await page.wait_for_load_state('networkidle')
                    # Attendre moins longtemps pour économiser la bande passante
                    vote_page_wait = 2000 if proxy_conf else 2000
                    await page.wait_for_timeout(vote_page_wait)
            except Exception as e:
                logging.warning("Bouton de vote initial non trouvé, on continue...")

            # --- 4. Remplissage du Pseudo sur serveur-prive.net ---
            logging.info("Saisie du pseudo sur la page de vote...")
            
            try:
                # Essayer plusieurs sélecteurs possibles pour le champ pseudo
                pseudo_selectors = [
                    "input#pseudo",
                    "input[name='pseudo']",
                    "input[name='username']",
                    "input#username",
                    "input[placeholder*='pseudo' i]",
                    "input[placeholder*='Pseudo' i]"
                ]
                
                pseudo_input = None
                for selector in pseudo_selectors:
                    try:
                        pseudo_input = await page.wait_for_selector(selector, timeout=5000)
                        if pseudo_input:
                            logging.info(f"Champ pseudo trouvé avec sélecteur: {selector}")
                            break
                    except:
                        continue
                
                if pseudo_input:
                    await pseudo_input.click()
                    await pseudo_input.fill(username)
                    await page.wait_for_timeout(1000)  # Délai réaliste
                    logging.info(f"Pseudo '{username}' saisi sur serveur-prive.")
                else:
                    logging.warning(f"⚠️ Aucun champ pseudo trouvé. Le pseudo est peut-être déjà pré-rempli.")
                    # Continuer quand même - peut-être que le pseudo est déjà pré-rempli
            except Exception as e:
                logging.warning(f"Erreur lors de la saisie du pseudo : {e}")
                # Continuer quand même
                    
            # --- 5. Interaction avec l'Iframe MTCaptcha ---
            logging.info("Recherche de l'iframe MTCaptcha...")
            try:
                # Timeout réduit pour économiser la bande passante
                iframe_timeout = 15000 if proxy_conf else 15000
                iframe_element = await page.wait_for_selector('iframe[src*="service.mtcaptcha.com"]', timeout=iframe_timeout)
                frame = await iframe_element.content_frame()
                
                # Attendre que l'image du captcha soit chargée
                await frame.wait_for_selector(".mtcap-image-mini", timeout=10000)
            except Exception as e:
                logging.error(f"❌ Impossible de trouver l'iframe MTCaptcha: {e}")
                logging.error(f"URL actuelle: {page.url}")
                raise
            
            # --- 6. Extraction de l'image (Base64) ---
            style = await frame.evaluate("document.querySelector('.mtcap-image-mini').style.backgroundImage")
            
            if 'url("data:image' in style or "url('data:image" in style:
                b64 = style.split("data:image/")[1].split('")')[0].split("')")[0]
                if "base64," in b64:
                    b64 = b64.split("base64,")[1]
                
                logging.info("Image Captcha extraite. Envoi à l'IA Mistral...")
                captcha_text = solve_mtcaptcha_with_mistral(b64)
                
                if captcha_text:
                    logging.info(f"L'IA a déchiffré : {captcha_text}")
                    
                    # Saisie dans le champ de l'iframe
                    input_field = await frame.query_selector("input[type='text']")
                    if input_field:
                        await input_field.type(captcha_text, delay=150)
                        logging.info("Texte saisi dans le captcha.")
                        await page.wait_for_timeout(1000)
                        await random_mouse_move(page)
                        
                    # --- 7. Validation finale du Vote ---
                    logging.info("Recherche du bouton de vote...")
                    # On essaie plusieurs sélecteurs courants
                    vote_selectors = ["button#btn-vote", "button.btn-vote", "input[type='submit']", "button:has-text('vote')"]
                    
                    btn_clicked = False
                    for selector in vote_selectors:
                        vote_btn = await page.query_selector(selector)
                        if vote_btn and await vote_btn.is_visible():
                            logging.info(f"Clic sur le bouton trouvé via '{selector}'")
                            await vote_btn.click()
                            btn_clicked = True
                            break
                    
                    if not btn_clicked:
                        logging.warning("Bouton de vote non trouvé avec les sélecteurs standards.")
                    
                    # Attendre moins longtemps pour économiser la bande passante
                    await page.wait_for_timeout(10000)
                    
                    # Vérifications multiples du succès
                    content = (await page.content()).lower()
                    page_url = page.url.lower()
                    
                    success_indicators = ["merci", "confirmé", "succès", "vote enregistré", "vote validé", "thank you", "vote counted"]
                    redirect_indicators = ["serenity-craft.fr", "redirect"]
                    
                    vote_success = any(indicator in content for indicator in success_indicators)
                    vote_redirect = any(indicator in page_url for indicator in redirect_indicators)
                    
                    if vote_success or vote_redirect:
                        logging.info("✅ Vote validé avec succès !")
                        # Attendre moins longtemps pour économiser la bande passante
                        await page.wait_for_timeout(3000)
                    else:
                        logging.warning("⚠️ Vote peut-être non validé. Vérification manuelle recommandée.")
                        # Log pour debug
                        logging.info(f"URL actuelle: {page_url}")
                        logging.info("Contenu de la page enregistré pour debug.")
                else:
                    logging.error("L'IA n'a pas renvoyé de réponse valide.")
            else:
                logging.error("Impossible de trouver l'image Base64 dans le widget.")

        except Exception as e:
            logging.error(f"Erreur durant l'exécution du vote : {e}")
            
        finally:
            await browser.close()

async def vote_serveur_minecraft_vote(username, proxy_conf=None):
    """Vote sur serveur-minecraft-vote.fr"""
    portal_url = "https://serenity-craft.fr/vote"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage', '--no-zygote']
        )
        ctx_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }
        if proxy_conf:
            ctx_args["proxy"] = proxy_conf
            
        context = await browser.new_context(**ctx_args)
        
        async def route_interceptor(route):
            res_type = route.request.resource_type
            url = route.request.url.lower()
            if "captcha" in url or "google" in url or "gstatic" in url:
                await route.continue_()
                return
            if res_type in ["image", "media", "font", "stylesheet"]:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", route_interceptor)
        page = await context.new_page()
        
        try:
            logging.info(f"🚀 Navigation vers le portail {portal_url}...")
            await page.goto(portal_url, wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            try:
                close_btn = await page.query_selector(".btn-close")
                if close_btn and await close_btn.is_visible():
                    await close_btn.click()
                    logging.info("Popup informatif fermé.")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logging.debug(f"Pas de popup à fermer ou erreur : {e}")
            
            pseudo_portal = await page.wait_for_selector("input#stepNameInput", timeout=15000)
            if pseudo_portal:
                await pseudo_portal.fill(username)
                await page.click("button[type='submit']")
                logging.info(f"✍️ Pseudo '{username}' saisi sur le portail.")
                await page.wait_for_timeout(2000)
                
            logging.info("🖱️ Recherche du lien serveur-minecraft-vote.fr...")
            portal_link = await page.wait_for_selector('a[href*="serveur-minecraft-vote.fr"]', timeout=10000)
            link_class = await portal_link.get_attribute("class")
            if link_class and "disabled" in link_class:
                logging.info(f"⏳ Le vote pour {username} est en cooldown sur le portail. Annulation du cycle.")
                return
                
            async with page.expect_popup() as popup_info:
                await portal_link.click()
            
            page = await popup_info.value
            await page.wait_for_load_state('networkidle')
            logging.info("✨ Nouvel onglet serveur-minecraft-vote.fr ouvert.")

            logging.info("🖱️ Recherche de l'onglet 'Voter'...")
            try:
                cookie_btn = await page.wait_for_selector(".js-cookie-consent-agree", timeout=3000)
                if cookie_btn and await cookie_btn.is_visible():
                    await cookie_btn.click()
            except:
                pass
            
            voter_tab = await page.wait_for_selector('a[href$="/vote"]', timeout=10000)
            if voter_tab:
                await voter_tab.click()
                await page.wait_for_load_state('networkidle')
                logging.info("✨ Onglet 'Voter' cliqué, page de vote chargée.")

            logging.info(f"✍️ Saisie du pseudo : {username}")
            pseudo_input = await page.wait_for_selector("input#pseudo", timeout=10000)
            if pseudo_input:
                await pseudo_input.click(force=True)
                await pseudo_input.fill(username)
                
            logging.info("🖱️ Recherche du bouton de vote...")
            vote_btn = await page.wait_for_selector("button#vote-button-action", timeout=10000)
            
            if vote_btn:
                btn_text = await vote_btn.inner_text()
                if "déconnecté" in btn_text.lower() or "voter" in btn_text.lower():
                    logging.info("✅ Bouton prêt. Clic en cours...")
                    await vote_btn.click()
                    await page.wait_for_timeout(5000)
                    
                    content = (await page.content()).lower()
                    if "merci" in content or "succès" in content or "confirmé" in content:
                        logging.info("✨ VOTE RÉUSSI sur serveur-minecraft-vote.fr !")
                    else:
                        logging.info("🏁 Cycle terminé. Vérifiez vos récompenses en jeu.")
                else:
                    logging.warning(f"⚠️ Le bouton semble indiquer que le vote n'est pas possible : {btn_text}")

        except Exception as e:
            logging.error(f"❌ Erreur durant le vote sur serveur-minecraft-vote.fr : {e}")
            
        finally:
            await browser.close()
            logging.info("🔒 Navigateur fermé.")

async def vote_serveur_minecraft_com(username, proxy_conf=None):
    """Vote sur serveur-minecraft.com avec reCAPTCHA"""
    portal_url = "https://serenity-craft.fr/vote"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage', '--no-zygote']
        )
        ctx_args = {
            "viewport": {'width': 1280, 'height': 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        }
        if proxy_conf:
            ctx_args["proxy"] = proxy_conf
            
        context = await browser.new_context(**ctx_args)
        
        async def route_interceptor(route):
            res_type = route.request.resource_type
            url = route.request.url.lower()
            if "captcha" in url or "google" in url or "gstatic" in url:
                await route.continue_()
                return
            if res_type in ["image", "media", "font", "stylesheet"]:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", route_interceptor)
        page = await context.new_page()
        
        try:
            logging.info(f"🌐 Navigation vers le portail {portal_url}...")
            max_retries = 3
            for i in range(max_retries):
                try:
                    await page.goto(portal_url, wait_until='networkidle', timeout=60000)
                    break
                except Exception as e:
                    if i == max_retries - 1: raise e
                    logging.warning(f"⚠️ Tentative {i+1} au portail échouée ({e}), nouvel essai...")
                    await page.wait_for_timeout(5000)

            await page.wait_for_timeout(2000)

            try:
                close_btn = await page.query_selector(".btn-close")
                if close_btn and await close_btn.is_visible():
                    await close_btn.click()
                    logging.info("Popup informatif fermé.")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logging.debug(f"Pas de popup à fermer ou erreur : {e}")
            
            pseudo_portal = await page.wait_for_selector("input#stepNameInput", timeout=15000)
            if pseudo_portal:
                await pseudo_portal.fill(username)
                await page.click("button[type='submit']")
                logging.info(f"✍️ Pseudo '{username}' saisi sur le portail.")
                await page.wait_for_timeout(3000)

            logging.info("🖱️ Recherche du lien serveur-minecraft.com...")
            portal_link = await page.wait_for_selector('a[href*="serveur-minecraft.com"]', timeout=10000)
            link_class = await portal_link.get_attribute("class")
            if link_class and "disabled" in link_class:
                logging.info(f"⏳ Le vote pour {username} est en cooldown sur le portail. Annulation du cycle.")
                return
                
            async with page.expect_popup() as popup_info:
                await portal_link.click()
            
            page = await popup_info.value
            await page.wait_for_load_state('domcontentloaded')
            logging.info("✨ Nouvel onglet serveur-minecraft.com ouvert.")
            await page.wait_for_timeout(10000)
            
            logging.info(f"👤 Saisie du pseudo: {username}")
            await page.wait_for_selector("input#form_username", timeout=15000)
            await page.fill("input#form_username", username)
            
            logging.info("🤖 Recherche du reCAPTCHA...")
            anchor_frame = None
            for frame in page.frames:
                if "anchor" in frame.url:
                    anchor_frame = frame
                    break
            
            if anchor_frame:
                logging.info("🖱️ Clic checkbox...")
                await anchor_frame.click("#recaptcha-anchor")
                await page.wait_for_timeout(4000)
                
                bframe = None
                for frame in page.frames:
                    if "bframe" in frame.url:
                        bframe = frame
                        break
                
                has_challenge = False
                if bframe:
                    try:
                        await bframe.wait_for_selector(".rc-imageselect-instructions", timeout=5000)
                        has_challenge = True
                    except:
                        has_challenge = False
                
                if has_challenge:
                    logging.info("🖼️ Défi reCAPTCHA détecté !")
                    
                    for attempt in range(3):
                        instr_text = await bframe.inner_text(".rc-imageselect-instructions")
                        instr_text = instr_text.replace("\n", " ").strip()
                        logging.info(f"📝 Défi: {instr_text}")
                        
                        grid = await bframe.wait_for_selector(".rc-imageselect-payload")
                        img_bytes = await grid.screenshot()
                        b64_img = base64.b64encode(img_bytes).decode('utf-8')
                        
                        tiles = solve_grid(b64_img, instr_text)
                        
                        if tiles:
                            all_tiles = await bframe.query_selector_all(".rc-imageselect-tile")
                            for t in tiles:
                                if 0 < t <= len(all_tiles):
                                    logging.info(f"🖱️ Clic case #{t}")
                                    await all_tiles[t-1].click()
                                    await page.wait_for_timeout(400)
                            
                            verify_btn = await bframe.wait_for_selector("#recaptcha-verify-button")
                            await verify_btn.click()
                            await page.wait_for_timeout(3000)
                            
                            if not await bframe.is_visible(".rc-imageselect-instructions"):
                                logging.info("✅ Défi résolu !")
                                break
                        else:
                            logging.warning("⚠️ Pas de réponse de l'IA, passage au cycle suivant.")
                            break
            
            logging.info("🗳️ Clique sur voter...")
            vote_btn = await page.wait_for_selector('button:has-text("Voter")')
            await vote_btn.scroll_into_view_if_needed()
            await vote_btn.click()
            await page.wait_for_timeout(5000)
            logging.info("✨ Vote terminé sur serveur-minecraft.com.")

        except Exception as e:
            logging.error(f"❌ Erreur durant le vote sur serveur-minecraft.com : {e}")
            
        finally:
            await browser.close()
            logging.info("🔒 Navigateur fermé.")

async def main_loop():
    cycle = 1
    while True:
        logging.info(f"=== Début du cycle de vote #{cycle} (Tous les sites) ===")
        
        for acc in ACCOUNTS:
            username = acc["username"]
            proxy_conf = acc["proxy"]
            
            logging.info(f"--- Vote pour {username} ---")
            
            # Vote sur serveur-prive.net
            try:
                await vote_serveur_prive(username, proxy_conf)
            except Exception as e:
                logging.error(f"Erreur vote serveur-prive.net: {e}")
            
            await asyncio.sleep(5)
            
            # Vote sur serveur-minecraft-vote.fr
            try:
                await vote_serveur_minecraft_vote(username, proxy_conf)
            except Exception as e:
                logging.error(f"Erreur vote serveur-minecraft-vote.fr: {e}")
            
            await asyncio.sleep(5)
            
            # Vote sur serveur-minecraft.com
            try:
                await vote_serveur_minecraft_com(username, proxy_conf)
            except Exception as e:
                logging.error(f"Erreur vote serveur-minecraft.com: {e}")
        
        logging.info(f"=== Fin du cycle de vote #{cycle} ===")
        logging.info(f"⏳ Prochain vote dans 1h30 (5400s)...")
        await asyncio.sleep(5430)
        cycle += 1

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("Arrêt du bot.")
        sys.exit(0)
