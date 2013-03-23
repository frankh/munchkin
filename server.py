import random
import cards
import logging
import threading
import json
import time
from enums import Moves, Phases
from collections import defaultdict
from ai import AI
from player import Player

log = logging.getLogger("MunchkinServer")
log.setLevel(logging.DEBUG)

#placeholder for gettext
def gettext(string):
	return string

_ = gettext

class CachedAttribute(object):    
    '''Computes attribute value and caches it in the instance.
    From the Python Cookbook (Denis Otkidach)
    This decorator allows you to create a property which can be computed once and
    accessed many times. Sort of like memoization.
    '''
    def __init__(self, method, name=None):
        # record the unbound-method and the name
        self.method = method
        self.name = name or method.__name__
        self.__doc__ = method.__doc__
    def __get__(self, inst, cls): 
        if inst is None:
            # instance attribute accessed on class, return self
            # You get here if you write `Foo.bar`
            return self
        # compute, cache and return the instance's attribute value
        result = self.method(inst)
        # setattr redefines the instance's attribute so this doesn't get called again
        setattr(inst, self.name, result)
        return result

class Deck(object):
	
	def __init__(self, game, id_generator):
		self.cards = []
		self.discards = []
		self.id_generator = id_generator
		self.game = game

	def add_to_deck(self, card_class, count=1):
		for i in range(count):
			new_card = card_class(self.game, self, self.id_generator.new_id())
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
			# remove old card id and re-add to game. This solution kind of sucks TODO make nice
			del self.game.cards[card.id]
			card.id = self.id_generator.new_id()
			self.game.cards[card.id] = card
	
class ClassicDoorDeck(Deck):
	def hidden_card(self, id):
		return cards.DoorCard(self.game, self, id)

	name = "Door"

	def __init__(self, game, id_generator):
		super().__init__(game, id_generator)
		self.add_to_deck(cards.MrBones, 10)
		self.add_to_deck(cards.UndeadHorse, 10)
		self.shuffle()

class ClassicTreasureDeck(Deck):
	def hidden_card(self, id):
		return cards.TreasureCard(self.game, self, id)
	name = "Treasure"

	def __init__(self, game, id_generator):
		super().__init__(game, id_generator)
		self.add_to_deck(cards.FreezingExplosivePotion, 20)
		self.add_to_deck(cards.SpikyKnees, 20)
		self.shuffle()

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

		if isinstance(target, dict):
			if target['type'] == 'card':
				self.target = game.card_from_id(target['id'])
			elif target['type'] == 'player':
				self.target = game.player_from_id(target['id'])
			elif target['type'] == 'combat':
				# target id should be either 'players' or 'monsters'.
				self.target = 'combat_'+target['id']
			else:
				raise Exception('TODO')


class Combat(object):

	def __init__(self, players, monster_cards):
		self.players, self.monster_cards = players, monster_cards
		self.player_modifier_cards = []
		self.monster_modifier_cards = []

	def players_win(self):
		return self.players_total() > self.monsters_total()

	def players_total(self):
		return sum(player.level+player.bonus for player in self.players)

	def monsters_total(self):
		return sum(monster.level+max(monster.bonus(player) for player in self.players) for monster in self.monster_cards)

	def treasures(self):
		return sum(monster.treasures for monster in self.monster_cards)

	def level_ups(self):
		return sum(monster.level_ups for monster in self.monster_cards)

	def info(self):
		return {
			'players': [player.id for player in self.players],
			'monster_cards': [card.info() for card in self.monster_cards],
		}

class EventSystem(object):
	id = 0

	def sched(self, func, delay):
		class SchedThread(threading.Thread):
			def run(self):
				time.sleep(delay)
				func()
		SchedThread().start()

	# Use a cached attributes so we don't need to call __init__
	@CachedAttribute
	def handlers(self):
		return defaultdict(list)

	@CachedAttribute
	def one_time_handlers(self):
		return defaultdict(list)

	def get_key(self, obj, event_name):
		return (obj.__class__, obj.id, event_name)

	def bind_once(self, event_name, func):
		return self.bind_once(self, event_name, func)

	def bind_once(self, obj, event_name, func):
		self.one_time_handlers[self.get_key(obj, event_name)].append(func)

	def bind(self, event_name, func):
		return self.bind(self, event_name, func)

	def bind(self, obj, event_name, func):
		self.handlers[self.get_key(obj, event_name)].append(func)

	def fire(self, event_name):
		return self.fire(self, event_name)

	def fire(self, obj, event_name):
		key = self.get_key(obj, event_name)

		for handler in self.handlers[key]:
			handler(obj)

		for handler in self.one_time_handlers[key]:
			handler(obj)

		# clear one-time handlers after firing.
		self.one_time_handlers[key] = []

class Game(EventSystem):
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

	def discard(self, card):
		for player in self.players:
			if card in player.hand:
				player.hand.remove(card)
			if card in player.carried:
				player.carried.remove(card)

		card.deck.discards.append(card)

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
		if player and player != self.current_player:
			self.broadcast_message("It is now "+player.name+"'s turn")
		self.broadcast_message("It is now the "+phase+" phase")

		self.current_player = player
		self.phase = phase
		
		self.update_valid_moves()
		self.timeout(15.0)

	def update_valid_moves(self):
		for player in self.players:
			player_moves = self.get_valid_moves(player)
			self.send(player, {'type': 'valid_moves', 'moves':player_moves})

			# If the player has no moves, auto-ready them. If their only move has no card, their only move is to ready. Ready them.
			# if (not player.ready) and ((not player_moves) or (len(player_moves) == 1 and None in player_moves)):
			# 	self.ready(player)

	def ready(self, player):
		self.broadcast_message(player.name + " is ready")
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

		elif self.phase == Phases.BEGIN:
			# Kick down the door!
			door_card = self.door_deck.draw()

			if isinstance(door_card, cards.Monster):
				self.combat = Combat([self.current_player], [door_card])

				self.broadcast({
					'type': 'combat',
					'combat': self.combat.info(),
				})

				self.change_phase(self.current_player, Phases.COMBAT)

		elif self.phase == Phases.COMBAT:
			if self.combat.players_win():
				self.broadcast_message("Player", self.combat.players[0].name, 
										"wins:", self.combat.treasures(), 
										"treasures and", self.combat.level_ups(), 
										"level ups")

				self.deal(self.combat.players[0], self.treasure_deck, face_up=len(self.combat.players)>1, count=self.combat.treasures())
				self.combat.players[0].level_up(count=self.combat.level_ups(), monster_kill=True)

				if self.combat.players[0].level >= 10:
					self.broadcast_message("Player", self.combat.players[0].name, 
										"wins!")
					self.change_phase(None, Phases.END)

			else:
				self.broadcast_message("Player", self.combat.players[0].name, 
										"loses! Bad stuff:", self.combat.monster_cards[0].bad_stuff.__doc__)

				for monster in self.combat.monster_cards:
					for player in self.combat.players:
						monster.bad_stuff(player)

			for card in self.combat.monster_cards:
				card.discard()

			for card in self.combat.player_modifier_cards + self.combat.monster_modifier_cards:
				if hasattr(card, 'discard'):
					card.discard()

			for player in self.combat.players:
				self.update_player(player)
				
			self.combat = None
			
			self.change_phase(self.current_player, Phases.POST_COMBAT)
		elif self.phase == Phases.POST_COMBAT:
			self.change_phase(self.players[(self.players.index(self.current_player) + 1) % len(self.players)], Phases.BEGIN)



	def setup(self):
		for player in self.players:
			self.deal(player, self.door_deck, count=4)
			self.deal(player, self.treasure_deck, count=4)

		self.change_phase(None, Phases.SETUP)
		self.timeout(10.0)

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

		return move.move_type == Moves.WAIT or (self.is_potentially_valid(move.move_type) \
			and move.card.can_play(move.move_type, move.target, self.phase, self.is_turn(player)))

	def is_potentially_valid(self, move):
		return move in self.potential_moves(self.phase)

	def potential_moves(self, phase):
		return {
			Phases.SETUP : [Moves.DONE, Moves.CARRY],
			Phases.BEGIN : [Moves.DRAW, Moves.CARRY, Moves.PLAY],
			Phases.PRE_DRAW : [Moves.DRAW, Moves.PLAY, Moves.CARRY],
			Phases.KICK_DOOR : [Moves.DRAW, Moves.PLAY, Moves.CARRY],
			Phases.COMBAT : [Moves.PLAY],
			Phases.POST_COMBAT : [Moves.PLAY, Moves.CARRY, Moves.DONE],
			Phases.LOOT_ROOM : [Moves.PLAY, Moves.CARRY, Moves.DONE],
			Phases.CHARITY : [Moves.PLAY, Moves.CARRY, Moves.DONE, Moves.GIVE],
			Phases.END : [],
		}[phase]

	def all_cards(self, player):
		return [card if ((not card.in_hand) or card in player.hand) else card.deck.hidden_card(card.id) for card in self.cards.values()]

	def get_valid_moves(self, player):
		potential = self.potential_moves(self.phase)
		valid = defaultdict(lambda: defaultdict(list))
		if Moves.DONE in potential:
			valid[None][Moves.DONE].append(None)
			potential.remove(Moves.DONE)

		phase_specific_targets = ["combat_monsters", "combat_players"] if self.phase == Phases.COMBAT else []

		for move in potential:
			for card in player.all_cards:
				for target in [None] + self.all_cards(player) + phase_specific_targets:
					if card.can_play(move, target, self.phase, self.is_turn(player)):
						valid[card.id][move].append(target.info() if hasattr(target, "info") else target)

		return valid

	def play_move(self, move):
		if not self.is_valid(move):
			raise Exception('INVALID MOVE')
		self.action_number += 1

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

		if move.move_type == Moves.PLAY:
			result, value = card.play(move.target)
			if result == 'attach_to_combat':
				if value == 'combat_players':
					self.combat.player_modifier_cards.append(card)
				elif value == 'combat_monsters':
					self.combat.monster_modifier_cards.append(card)
				else:
					raise Exception('Invalid target')

				card.in_hand = False

				if card in player.hand:
					player.hand.remove(card)

				if card in player.carried:
					player.carried.remove(card)

		self.update_player(player)
		self.update_valid_moves()
		self.timeout(15.0)

	def timeout(self, timeout):
		current_action = self.action_number

		def ready_players():
			if self.action_number == current_action:
				for player in self.players:
					self.ready(player)

		self.sched(ready_players, timeout)
		self.broadcast({
			'type': 'timeout',
			'timeout': timeout*1000,
		})

	def all_carried_cards(self):
		pass

	def broadcast_message(self, *args):
		for player in self.players:
			self.send(player, {
				'type': 'message',
				'message': {
					'from': 'system',
					'private': False,
					'text': ' '.join(map(str,args))
				}
			})

	def send(self, player, obj):
		obj = dict(obj)
		obj['action_number'] = self.action_number

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
			if 'AI' in game_id:
				games[game_id].add_player(AI('ROBOT', self))
			
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
		elif if message['type'] == "READY":
			self.game.ready(self.player)

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
		log.debug('Listening on port 8888')
		iol = tornado.ioloop.IOLoop.instance()
		tornado.ioloop.PeriodicCallback(lambda: None,500,iol).start()
		iol.start()
	except BaseException as e:
		for game in games.values():
			game.killed = True
		raise e
