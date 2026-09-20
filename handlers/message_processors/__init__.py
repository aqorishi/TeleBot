from .no_nedd_handler.process_alwayswin import handle as handle_alwayswin
from .no_nedd_handler.process_aman import handle as handle_aman
from .process_binancekillers import handle as handle_binancekillers
from .process_binancekillersvip import handle as handle_binancekillersvip
from .process_fearandgreed import handle as handle_fearandgreed
from .no_nedd_handler.process_fedrussian import handle as handle_fedrussian
from .process_guru import handle as handle_guru
from .process_pfw import handle as handle_pfw
from .process_pfwpremium import handle as handle_pfwpremium
from .no_nedd_handler.process_wolfx import handle as handle_wolfx



# IDs same for the labels, they should match the channel names in your config.py
PROCESSOR_MAP = {
    "-1001288549616": {"label": "AlwaysWin", "handler": handle_alwayswin},
    "-1001744711450": {"label": "Aman", "handler": handle_aman},
    "-1001220789766": {"label": "BinanceKillers", "handler": handle_binancekillers},
    "-1001556597544": {"label": "BinanceKillersvip", "handler": handle_binancekillersvip},
    "-1002250488311": {"label": "FearAndGreed", "handler": handle_fearandgreed},
    "-1001701261905": {"label": "FedRussianVIP", "handler": handle_fedrussian},
    "-1001556054753": {"label": "WatcherGuru", "handler": handle_guru},
    "-4669780859"   : {"label": "PFWRobot", "handler": handle_pfw},
    "-1002174598690": {"label": "PFWPremium", "handler": handle_pfwpremium},
    "-1001394941879": {"label": "wolfxX", "handler": handle_wolfx},
}

def get_processor(chat_id: str):
    return PROCESSOR_MAP.get(str(chat_id))
