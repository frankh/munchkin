import json
from enums import Moves, Phases

IMAGE_ROOT = 'res/'

class Card(object):
	def __init__(self, deck, id):
		self.id = id
		self.in_hand = True
		self.deck = deck

	def can_play(self, move, phase, in_turn):
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

	def bonus(self, player):
		return 0

	def on_escape(self, player):
		pass

	def can_flee(self, player):
		return True

	def bad_stuff(self, player):
		pass

	def can_play(self, move, phase, in_turn):
		return super().can_play(move, phase, in_turn) or \
		    (move == Moves.FIGHT and self.in_hand and in_turn)

	def info(self, player=None):
		d = super().info(player)
		d['level'] = self.level
		if player:
			d['bonus'] = self.bonus(player)

		return d

class Item(TreasureCard):
	name = "Unimplemented Item"
	bonus = 0

	image = "treasure_back.png"

	def bonus_on_player(self, player):
		return self.bonus

	def can_equip(self, player):
		return True

	def can_play(self, move, phase, in_turn):
		return super().can_play(move, phase, in_turn) or \
		    (move == Moves.CARRY and self.in_hand and in_turn)

	def info(self, player=None):
		d = super().info(player)
		d['bonus'] = self.bonus
		return d

class CombatOneShot(Item):
	def can_equip(self, player):
		return False

	def can_play(self, move, phase, in_turn):
		return super().can_play(move, phase, in_turn) or \
			(move == Moves.PLAY and phase == Phases.COMBAT)

class MagicMissile(CombatOneShot):
	name = "Magic Missile"
	image = "MagicMissile.jpg"

class FreezingExplosivePotion(CombatOneShot):
	name = "Freezing Explosive Potion"
	image = "FreezingExplosivePotion.jpg"

class SpikyKnees(Item):
	name = "Spiky Knees"
	image = "Spiky_Knees.jpg"

	bonus = 1

class MrBones(Monster):
	name = "Mr. Bones"
	image = "MrBones.jpg"

	level = 2
	treasure = 1

	def bad_stuff(self, player):
		"""His bony touch costs you 2 levels."""
		player.level_down()
		player.level_down()

class UndeadHorse(Monster):
	name = "Undead Horse"
	image = "Undead_Horse.jpg"

	level = 4
	treasure = 2

	def bonus(self, player):
		"""+5 Against Dwarves"""
		if player.race == "dwarf":
			return 5
		return 0

	def bad_stuff(self, player):
		"""Kicks, bites, and smells awful. Lose 2 levels."""
		player.level_down()
		player.level_down()
