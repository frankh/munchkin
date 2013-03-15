import json
from enums import Moves, Phases

IMAGE_ROOT = 'res/'

class Card(object):
	def __init__(self, game, deck, id):
		self.id = id
		self.in_hand = True
		self.deck = deck
		self.game = game

	def discard(self):
		self.game.discard(self)

	def can_play(self, move, target, phase, in_turn):
		return False

	def info(self, player=None):
		return {
			'id': self.id,
			'name': self.name,
			'image': IMAGE_ROOT+self.image,
		}

class DoorCard(Card):
	name = "Door Card"
	image = "room_back.png"

class TreasureCard(Card):
	name = "Treasure Card"
	image = "treasure_back.png"

class Monster(DoorCard):
	level = 1

	level_ups = 1
	treasures = 1

	def bonus(self, player=None):
		return 0

	def on_escape(self, player):
		pass

	def can_flee(self, player):
		return True

	def bad_stuff(self, player):
		"""NO BAD STUFF"""
		pass

	def can_play(self, move, target, phase, in_turn):
		return super().can_play(move, target, phase, in_turn) or \
		    (move == Moves.FIGHT and self.in_hand and in_turn and target == None)

	def info(self, player=None):
		d = super().info(player)
		d['level'] = self.level
		if player:
			d['bonus'] = self.bonus(player)

		return d

class Item(TreasureCard):
	name = "Unimplemented Item"
	bonus = 0
	value = None

	image = "treasure_back.png"

	def bonus_on_player(self, player):
		return self.bonus

	def can_equip(self, player):
		return True

	def can_play(self, move, target, phase, in_turn):
		return super().can_play(move, target, phase, in_turn) or \
		    (move == Moves.CARRY and self.in_hand and in_turn and target == None)

	def info(self, player=None):
		d = super().info(player)
		d['bonus'] = self.bonus
		return d

class CombatOneShot(Item):
	def can_equip(self, player):
		return False

	def play(self, target):
		return ('attach_to_combat', target)

	def can_play(self, move, target, phase, in_turn):
		return super().can_play(move, target, phase, in_turn) or \
			(move == Moves.PLAY and phase == Phases.COMBAT and target in ("combat_players", "combat_monsters"))

class MagicMissile(CombatOneShot):
	name = "Magic Missile"
	image = "MagicMissile.jpg"
	value = 100

class FreezingExplosivePotion(CombatOneShot):
	name = "Freezing Explosive Potion"
	image = "FreezingExplosivePotion.jpg"
	value = 100

class SpikyKnees(Item):
	name = "Spiky Knees"
	image = "Spiky_Knees.jpg"
	value = 100
	bonus = 1

class MrBones(Monster):
	name = "Mr. Bones"
	image = "MrBones.jpg"

	level = 2
	treasures = 1

	def bad_stuff(self, player):
		"""His bony touch costs you 2 levels."""
		player.level_down()
		player.level_down()

class UndeadHorse(Monster):
	name = "Undead Horse"
	image = "Undead_Horse.jpg"

	level = 4
	treasures = 2

	def bonus(self, player):
		"""+5 Against Dwarves"""
		if player.race == "dwarf":
			return 5
		return 0

	def bad_stuff(self, player):
		"""Kicks, bites, and smells awful. Lose 2 levels."""
		player.level_down()
		player.level_down()
