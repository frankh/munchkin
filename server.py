import random
import cards
import logging
import threading
import json
from enums import Moves, Phases
from collections import defaultdict

log = logging.getLogger("MunchkinServer")
log.setLevel(logging.DEBUG)

#placeholder for gettext
def gettext(string):
	return string

_ = gettext


class Deck(object):
	
	def __init__(self, game, id_generator):
		self.cards = []
		self.discards = []
		self.id_generator = id_generator
		self.game = game

	def add_to_deck(self, card, count=1):
		for i in range(count):
			new_card = card(self, self.id_generator.new_id())
			self.cards.append(new_card)
			self.game.cards[new_card.id] = new_card

	def draw(self):
		if not self.cards:
			self.reset()

		return self.cards.pop()
		
	def reset(self):
		self.cards = self.cards + self.discards
		self.discards = []
		self.shuffle()

	def shuffle(self, discards=False):
		if discards:
			random.shuffle(self.discards)
		else:
			random.shuffle(self.cards)

		# Regenerate the id's after the cards have been shuffled so that you can't track the ids.
		for card in self.cards:
			card.id = self.id_generator.new_id()
	
class ClassicDoorDeck(Deck):
	def hidden_card(self, id):
		return cards.DoorCard(self, id)

	name = "Door"

	def __init__(self, game, id_generator):
		super().__init__(game, id_generator)
		self.add_to_deck(cards.MrBones, 10)
		self.add_to_deck(cards.UndeadHorse, 10)
		self.shuffle()

class ClassicTreasureDeck(Deck):
	def hidden_card(self, id):
		return cards.TreasureCard(self, id)
	name = "Treasure"

	def __init__(self, game, id_generator):
		super().__init__(game, id_generator)
		self.add_to_deck(cards.FreezingExplosivePotion, 10)
		self.add_to_deck(cards.SpikyKnees, 10)
		self.shuffle()

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

	def level_up(self, monster_kill=False):
		if monster_kill:
			self.level += 1
		else:
			self.level = min(9, self.level+1)

	def level_down(self):
		self.level = max(1, self.level-1)

	def equip(self, card):
		self.bonus += card.bonus_on_player(self)

	@property
	def all_cards(self):
		yield from self.hand
		yield from self.carried


class IdHolder(object):
	def __init__(self):
		self.current_id = 0

	def new_id(self):
		self.current_id += 1
		return self.current_id

class Move(object):
	def __init__(self, game, move_type, player, card, target):
		self.move_type, self.player, self.card, self.target = move_type, player, card, target

		if not isinstance(card, cards.Card):
			self.card = game.card_from_id(card)

		if not isinstance(player, Player):
			self.player = game.player_from_id(player)

class Combat(object):
	pass

class Game(object):

	def __init__(self, password=None):
		id_generator = IdHolder()

		self.players = []
		self.cards = {}
		self.password = password
		self.started = False
		self.killed = False
		self.action_number = 1
		self.phase = None
		self.current_player = None

		self.door_deck = ClassicDoorDeck(self, id_generator)
		self.treasure_deck = ClassicTreasureDeck(self, id_generator)

	def card_from_id(self, id):
		return self.cards[int(id)]

	def player_from_id(self, id):
		return self.players[int(id)]

	def update_player(self, player):
		for other_player in self.players:
			self.send(other_player, {
				'type': 'player',
				'player': player.info(other_player)
			})

	def update_players(self):
		for p_id, player in enumerate(self.players):
			player.id = p_id

		for other_player in self.players:
			self.send(other_player, {
				'type': "players",
				'players': [player.info(other_player) for player in self.players],
			})

		if self.phase:
			self.update_valid_moves()

	def add_player(self, player):
		self.players.append(player)

		self.update_players()

		if len(self.players) == 2:
			self.broadcast_message("Starting game!")
			game = self
			class GameThread(threading.Thread):
				def run(self):
					game.start()

			GameThread().start()

	def change_phase(self, player, phase):
		self.current_player = player
		self.phase = phase

		if player:
			self.broadcast_message("It is now "+player.name+"'s turn")
		
		self.update_valid_moves()

	def update_valid_moves(self):
		for player in self.players:
			player_moves = self.get_valid_moves(player)
			self.send(player, {'type': 'valid_moves', 'moves':player_moves})

			# If the player has no moves, auto-ready them. If their only move has no card, their only move is to ready. Ready them.
			if (not player.ready) and ((not player_moves) or (len(player_moves) == 1 and None in player_moves)):
				self.broadcast_message(player.name + " is ready")
				self.ready(player)

	def ready(self, player):
		player.ready = True
		all_ready = True

		for player in self.players:
			all_ready &= player.ready

		if all_ready:
			for player in self.players:
				player.ready = False

			self.next_phase()

	def next_phase(self):
		if self.phase == Phases.SETUP:
			self.change_phase(random.choice(self.players), Phases.BEGIN)

		if self.phase == Phases.BEGIN:
			# Kick down the door!
			door_card = self.door_deck.draw()

			if isinstance(door_card, cards.Monster):
				self.combat = Combat([self.current_player], [door_card])

				self.change_phase(self.current_player, Phases.COMBAT)
				self.broadcast({
					'type': 'combat',
					'players': [self.current_player.id],
					'monsters': door_card.info(self.current_player)
				})

	def setup(self):
		for player in self.players:
			self.deal(player, self.door_deck, count=4)
			self.deal(player, self.treasure_deck, count=4)

		self.change_phase(None, Phases.SETUP)

	def start(self):
		log.debug("Starting game")

		self.started = True
		self.setup()
		
		#while not self.killed:
		#	self.clock.tick(10)

	def is_turn(self, player):
		return (not self.current_player) or (player == self.current_player)

	def is_valid(self, move):
		player = move.player
		return self.is_potentially_valid(move.move_type) \
			and move.card.can_play(move.move_type, player, self.is_turn(player))

	def is_potentially_valid(self, move):
		return move in self.potential_moves(self.phase)

	def potential_moves(self, phase):
		return {
			Phases.SETUP : [Moves.DONE, Moves.CARRY],
			Phases.BEGIN : [Moves.DRAW, Moves.CARRY, Moves.PLAY],
			Phases.PRE_DRAW : [Moves.DRAW, Moves.PLAY, Moves.CARRY],
			Phases.KICK_DOOR : [Moves.DRAW, Moves.PLAY, Moves.CARRY],
			Phases.COMBAT : [Moves.PLAY, Moves.CARRY],
			Phases.POST_COMBAT : [Moves.PLAY, Moves.CARRY, Moves.DONE],
			Phases.LOOT_ROOM : [Moves.PLAY, Moves.CARRY, Moves.DONE],
			Phases.CHARITY : [Moves.PLAY, Moves.CARRY, Moves.DONE, Moves.GIVE],
		}[phase]

	def get_valid_moves(self, player):
		potential = self.potential_moves(self.phase)
		valid = defaultdict(list)
		if Moves.DONE in potential:
			valid[None].append({'targets': None, 'move': Moves.DONE})
			potential.remove(Moves.DONE)

		for move in potential:
			for card in player.all_cards:
				if card.can_play(move, self.phase, self.is_turn(player)):
					valid[card.id].append({'targets': None, 'type': move})
				else:
					log.debug("can't "+str(move)+" "+str(card.name))

		return valid

	def play_move(self, move):
		if not self.is_valid(move):
			raise Exception('INVALID MOVE')

		card, player = move.card, move.player

		if move.move_type == Moves.CARRY:
			player.hand.remove(card)
			player.carried.append(card)
			card.in_hand = False

			if card.can_equip(player):
				self.broadcast_message(player.name, 'equipped', card.name)
				player.equip(card)
			else:
				self.broadcast_message(player.name, 'is carrying', card.name)

			self.update_player(player)
			self.update_valid_moves()

	def all_carried_cards(self):
		pass

	def broadcast_message(self, *args):
		for player in self.players:
			self.send(player, {
				'type': 'message',
				'message': {
					'from': 'system',
					'private': False,
					'text': ' '.join(args)
				}
			})

	def send(self, player, obj):
		obj = dict(obj)
		obj['action_number'] = self.action_number
		self.action_number += 1

		log.debug(str(player.id)+"> "+json.dumps(obj))

		if player.connection:
			player.connection.write_message(json.dumps(obj))

	def broadcast(self, obj):
		for player in self.players:
			self.send(player, obj)

	def deal(self, player, deck, face_up=False, count=1):
		for i in range(count):
			card = deck.draw()

			player.hand.append(card)

			for current_player in self.players:
				self.send(current_player, {
					'player': player.id,
					'type': "draw",
					'card': card.info() if player == current_player or face_up else deck.hidden_card(card.id).info(),
				})

games = {}

import tornado.web
import tornado.ioloop
import tornado.options
import tornado.httpserver
import tornado.websocket
from temp import FileHandler

application = tornado.web.Application([
	(r"/(.*)", FileHandler),
])

class ClientError(object):
	def __init__(self, message):
		self.message = "Invalid Move: " + message

	def __str__(self):
		return json.dumps({
			type: "error",
			message: self.message,
		})

class InvalidMove(ClientError):
	pass


class ClientSocket(tornado.websocket.WebSocketHandler):
	def open(self, username, game_id, password):
		username = username.decode('utf-8')
		game_id = game_id.decode('utf-8')
		
		if password:
			password = password.decode('utf-8')

		global games
		if game_id not in games:
			games[game_id] = Game(password)
			
		game = games[game_id]
		self.game = game

		if game.password and game.password != password:
			self.write_message(ClientError(_("Wrong password")))
			self.close()
			return

		if game.started:
			log.debug("Game already started")
			for player in game.players:
				if not player.connected:
					self.player = player
					player.connected = True
					player.connection = self
					game.update_players()
					return

			self.write_message(ClientError(_("Cannot join game, already in progress.")))
			self.close()
			return

		player = Player(username, self)
		game.add_player(player)

		self.player = player

		log.debug(username+"joined"+game_id)

	def on_message(self, message):
		log.debug(str(self.player.id)+'<'+message)
		message = json.loads(message)
	
		if message['type'] == "ACTION":
			move = Move(self.game, **message['action'])
			if self.game.is_valid(move):
				log.debug("Playing move "+json.dumps(message))
				self.game.play_move(move)
			else:
				log.debug("Invalid move: "+json.dumps(message))
				self.write_message("INVALID MOVE")
				return

	def on_close(self):
		if hasattr(self, 'game'):
			if self.game.started:
				self.player.connected = False
				self.player.connection = None
			else:
				self.game.players.remove(self.player)

socket_app = tornado.web.Application([
	(r"/socket/(?P<username>\w+)/(?P<game_id>\w+)(?:/(?P<password>\w+))?", ClientSocket),
])

if __name__ == '__main__':
	try:
		tornado.options.enable_pretty_logging()
		http_server = tornado.httpserver.HTTPServer(application)
		http_server.listen(8888)
		socket_app.listen(800)
		tornado.ioloop.IOLoop.instance().start()
	except BaseException as e:
		for game in games.values():
			game.killed = True
		raise e
