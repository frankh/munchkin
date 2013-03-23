import logging

log = logging.getLogger("MunchkinServer")

class Player(object):

	def __init__(self, name, connection):
		self.level = 1
		self.bonus = 0
		self.id = 0
		self.hand = []
		self.carried = []
		self.name = name
		self.connected = True
		self.connection = connection
		self.ready = False
		self.race = None

	def info(self, other_player=None):
		show_hand = other_player == None or other_player == self

		log.debug([(card.name, card.id) for card in self.hand])
		log.debug([(card.name, card.id) for card in self.carried])
		return {
			'name': self.name, 
			'id': self.id,
			'level': self.level,
			'bonus': self.bonus,
			'total': self.total,
			'hand': [card.info() if show_hand else card.deck.hidden_card(card.id).info() for card in self.hand],
			'carried': [card.info() for card in self.carried],
		}

	@property
	def total(self):
		return self.level + self.bonus

	def level_up(self, count=1, monster_kill=False):
		if monster_kill:
			self.level += count
		else:
			self.level = min(9, self.level+count)

	def level_down(self):
		self.level = max(1, self.level-1)

	def equip(self, card):
		self.bonus += card.bonus_on_player(self)

	@property
	def all_cards(self):
		yield from self.hand
		yield from self.carried
