#!/usr/bin/env python3
"""
TELEGRAM URL PROMOTER v2.2
Versione con messaggio personalizzabile (template)
"""

import asyncio
import json
import logging
import random
import sys
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, RPCError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Chat, Channel

# ==================== CONFIGURAZIONE ====================
class Config:
    """Gestione configurazione"""
    CONFIG_FILE = "config.json"

    @staticmethod
    def load():
        """Carica o crea configurazione"""
        if not os.path.exists(Config.CONFIG_FILE):
            print("⚠️  Configurazione non trovata!")
            print("🔄 Creo configurazione di default...")

            default_config = {
                "api_id": 0,
                "api_hash": "",
                "phone_number": "",
                "gruppo_url": "https://t.me/+",
                "canale_url": "https://t.me/+",
                "message_template": "",
                "interval_minutes": 30,
                "random_delay": 5,
                "working_hours": {"start": 9, "end": 23},
                "excluded_keywords": ["test", "privato", "famiglia", "lavoro", "admin", "staff", "riservato"]
            }

            with open(Config.CONFIG_FILE, "w") as f:
                json.dump(default_config, f, indent=4)

            print("✅ Configurazione creata in config.json")
            print("📝 MODIFICA config.json con le tue credenziali prima di avviare!")
            sys.exit(0)

        with open(Config.CONFIG_FILE, "r") as f:
            return json.load(f)

    @staticmethod
    def validate(config):
        """Valida la configurazione"""
        required = ["api_id", "api_hash", "phone_number"]
        for field in required:
            if not config.get(field):
                print(f"❌ Campo mancante in config.json: {field}")
                sys.exit(1)

        if config["api_id"] == 0:
            print("❌ api_id non valido! Ottienilo da: https://my.telegram.org")
            sys.exit(1)

        # Almeno uno tra gruppo_url e main_group_url deve essere presente
        if not config.get("gruppo_url") and not config.get("main_group_url"):
            print("❌ Inserisci almeno un link (gruppo_url o main_group_url)")
            sys.exit(1)

        return True

# ==================== LOGGING ====================
def setup_logging():
    """Configura il logging"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Handler per console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(console)

    # Handler per file
    file_handler = logging.FileHandler('promoter.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    return logger

# ==================== PROMOTER ====================
class URLPromoter:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.client = None
        self.running = False
        self.stats = {
            "total_sent": 0,
            "total_groups": 0,
            "errors": 0,
            "start_time": None
        }

    async def connect(self):
        """Connette a Telegram"""
        try:
            self.client = TelegramClient(
                'user_session',
                self.config['api_id'],
                self.config['api_hash']
            )

            await self.client.start(phone=self.config['phone_number'])

            if not await self.client.is_user_authorized():
                self.logger.error("❌ Autorizzazione fallita")
                return False

            me = await self.client.get_me()
            self.logger.info(f"✅ Connesso come: {me.first_name} (@{me.username})")
            return True

        except Exception as e:
            self.logger.error(f"❌ Errore connessione: {e}")
            return False

    def should_exclude(self, title: str) -> bool:
        """Controlla se escludere un gruppo in base alle parole chiave"""
        title_lower = title.lower()
        for keyword in self.config['excluded_keywords']:
            if keyword.lower() in title_lower:
                return True
        return False

    async def get_groups(self) -> List[Dict]:
        """Ottieni lista gruppi gestendo errori di accesso"""
        groups = []

        try:
            result = await self.client(GetDialogsRequest(
                offset_date=None,
                offset_id=0,
                offset_peer=InputPeerEmpty(),
                limit=200,
                hash=0
            ))

            for dialog in result.dialogs:
                try:
                    entity = await self.client.get_entity(dialog.peer)

                    # Verifica se è un gruppo (Chat) o un supergruppo (Channel con megagroup=True)
                    is_group = False
                    if isinstance(entity, Chat):
                        is_group = True
                    elif isinstance(entity, Channel) and getattr(entity, 'megagroup', False):
                        is_group = True

                    if is_group:
                        group_info = {
                            'id': entity.id,
                            'title': entity.title,
                            'username': getattr(entity, 'username', None)
                        }

                        if not self.should_exclude(group_info['title']):
                            groups.append(group_info)
                except RPCError as e:
                    # Salta dialoghi a cui non si ha accesso (privati, bannati, etc.)
                    self.logger.debug(f"Salto dialogo per RPCError: {e}")
                    continue
                except Exception as e:
                    self.logger.debug(f"Salto dialogo per errore generico: {e}")
                    continue

            self.stats['total_groups'] = len(groups)
            self.logger.info(f"📋 Trovati {len(groups)} gruppi validi")
            return groups

        except Exception as e:
            self.logger.error(f"❌ Errore recupero gruppi: {e}")
            return []

    async def send_url(self, group_info: Dict) -> bool:
        """Invia messaggio personalizzato al gruppo"""
        try:
            entity = await self.client.get_entity(group_info['id'])

            # Costruzione del messaggio
            if 'message_template' in self.config:
                # Usa il template con i placeholder
                gruppo = self.config.get('gruppo_url', self.config.get('main_group_url', ''))
                canale = self.config.get('canale_url', '')
                messaggio = self.config['message_template'].format(gruppo=gruppo, canale=canale)
            else:
                # Vecchio comportamento: solo URL
                messaggio = self.config.get('main_group_url', '')

            if not messaggio:
                self.logger.warning("⚠️ Nessun messaggio da inviare")
                return False

            await self.client.send_message(entity, messaggio, link_preview=False)

            self.stats['total_sent'] += 1
            self.logger.info(f"✅ Messaggio inviato a: {group_info['title']}")
            return True

        except FloodWaitError as e:
            self.logger.warning(f"⏳ FloodWait: {e.seconds}s - Attendo...")
            await asyncio.sleep(e.seconds + 2)
            return False

        except ChatWriteForbiddenError:
            self.logger.warning(f"🚫 Non posso scrivere in: {group_info['title']}")
            return False

        except Exception as e:
            self.logger.error(f"❌ Errore con {group_info['title']}: {str(e)[:100]}")
            self.stats['errors'] += 1
            return False

    def is_working_time(self) -> bool:
        """Controlla orario di lavoro"""
        now = datetime.now()
        current_hour = now.hour

        start = self.config['working_hours'].get('start', 0)
        end = self.config['working_hours'].get('end', 24)

        return start <= current_hour < end

    def show_banner(self):
        """Mostra banner iniziale"""
        print("\n" + "="*50)
        print("🚀 TELEGRAM URL PROMOTER v2.2")
        print("="*50)
        gruppo = self.config.get('gruppo_url', self.config.get('main_group_url', 'N/D'))
        canale = self.config.get('canale_url', 'N/D')
        print(f"📢 Gruppo: {gruppo}")
        print(f"📢 Canale: {canale}")
        print(f"⏰ Intervallo: {self.config['interval_minutes']} minuti")
        print(f"⏱️  Orario: {self.config['working_hours']['start']}:00 - {self.config['working_hours']['end']}:00")
        print("="*50 + "\n")

    async def run_promotion_cycle(self):
        """Esegue un ciclo completo di promozione"""
        self.logger.info("🔄 Avvio ciclo promozione...")

        if not self.is_working_time():
            self.logger.info("🌙 Fuori orario lavorativo")
            return

        groups = await self.get_groups()

        if not groups:
            self.logger.warning("⚠️  Nessun gruppo disponibile")
            return

        # Mescola i gruppi per ordine casuale
        random.shuffle(groups)

        success_count = 0
        for group in groups:
            if not self.running:
                break

            if await self.send_url(group):
                success_count += 1
                # Delay tra un invio e l'altro (1-3 secondi)
                await asyncio.sleep(random.uniform(1, 3))

        self.logger.info(f"📊 Ciclo completato: {success_count}/{len(groups)} invii riusciti")

    async def main_loop(self):
        """Loop principale"""
        self.running = True
        self.stats['start_time'] = datetime.now()

        self.show_banner()

        if not await self.connect():
            self.logger.error("❌ Impossibile connettersi a Telegram")
            return

        self.logger.info("✅ Promoter avviato correttamente!")

        while self.running:
            try:
                await self.run_promotion_cycle()

                # Calcola prossimo ciclo
                interval = self.config['interval_minutes'] * 60
                delay = interval + random.randint(0, self.config['random_delay'] * 60)

                next_run = datetime.now() + timedelta(seconds=delay)
                self.logger.info(f"⏰ Prossimo ciclo: {next_run.strftime('%H:%M:%S')}")

                # Conto alla rovescia
                for remaining in range(delay, 0, -60):
                    if not self.running:
                        break
                    if remaining % 300 == 0:  # Ogni 5 minuti
                        self.logger.info(f"⏳ Rimanenti: {remaining//60} minuti")
                    await asyncio.sleep(min(60, remaining))

            except KeyboardInterrupt:
                self.logger.info("🛑 Arresto richiesto...")
                break
            except Exception as e:
                self.logger.error(f"❌ Errore nel loop: {e}")
                await asyncio.sleep(60)

    def stop(self):
        """Arresta il promoter e mostra statistiche finali"""
        self.running = False

        if self.stats['start_time']:
            runtime = datetime.now() - self.stats['start_time']
            hours = runtime.seconds // 3600
            minutes = (runtime.seconds % 3600) // 60

            print("\n" + "="*50)
            print("📊 STATISTICHE FINALI")
            print("="*50)
            print(f"⏱️  Tempo esecuzione: {hours}h {minutes}m")
            print(f"📤 URL inviati: {self.stats['total_sent']}")
            print(f"📊 Gruppi monitorati: {self.stats['total_groups']}")
            print(f"❌ Errori: {self.stats['errors']}")
            print("="*50)

# ==================== MAIN ====================
async def main():
    """Funzione principale"""
    # Carica configurazione
    config = Config.load()
    Config.validate(config)

    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Avvia promoter
    promoter = URLPromoter(config)

    try:
        await promoter.main_loop()
    except KeyboardInterrupt:
        logger.info("\n👋 Arresto richiesto dall'utente")
    finally:
        promoter.stop()

if __name__ == "__main__":
    # Verifica Python 3.7+
    if sys.version_info < (3, 7):
        print("❌ Richiesto Python 3.7 o superiore")
        sys.exit(1)

    # Verifica dipendenze
    try:
        import telethon
    except ImportError:
        print("📦 Installa dipendenze: pip install telethon")
        sys.exit(1)

    # Esegui

    asyncio.run(main())
