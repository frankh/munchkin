def enum(*sequential, **named):
	enums = dict(zip(sequential, map(str, sequential)), **named)
	return type('Enum', (), enums)


Phases = enum(
	'SETUP',
	'BEGIN',
	'PRE_DRAW',
	'KICK_DOOR',
	'COMBAT',
	'POST_COMBAT',
	'LOOT_ROOM',
	'CHARITY',
)

Moves = enum(
	'DRAW',
	'CARRY',
	'PLAY',
	'FIGHT',
	'GIVE',
	'DONE'
)