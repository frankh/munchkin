import json
from player import Player
import logging

log = logging.getLogger("MunchkinServer")

class AI(Player):
	def __init__(self, name, connection):
		super().__init__(name, AIConnection(self))


class AIConnection(object):
	def __init__(self, player):
		self.player = player

	def write_message(self, message):
		msg = json.loads(message)