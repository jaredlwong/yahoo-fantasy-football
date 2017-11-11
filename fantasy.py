import csv
import simplejson as json
import logging
import pprint
from decimal import Decimal

import pandas as pd
from yahoo_oauth import OAuth2


oauth_logger = logging.getLogger('yahoo_oauth')
oauth_logger.disabled = True

oauth = OAuth2(None, None, from_file='oauth2.json')

if not oauth.token_is_valid():
    oauth.refresh_access_token()


# game_key = '371'

# response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/games;game_keys=371?format=json')
# print(response.text)

# response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/users;use_login=1/games;game_keys=nfl/leagues?format=json')
# print(response.text)
league_key = '371.l.52839'
league_id = '52839'

# response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/%s/transactions?format=json' % league_key)
# print(response.text)


def print_json(o):
    print(json.dumps(o, indent=2, sort_keys=True, use_decimal=True))


def is_array(d):
    if 'count' not in d:
        return False
    keys = set(d.keys())
    keys.remove('count')
    int_keys = set()
    for k in keys:
        try:
            int_keys.add(int(k))
        except ValueError:
            return False
    min_key = min(int_keys)
    max_key = max(int_keys)
    if min_key != 0:
        return False
    if len(int_keys) != (max_key - min_key + 1):
        return False
    return True


def convert_value(value):
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    elif isinstance(value, int):
        return value
    elif isinstance(value, dict):
        if is_array(value):
            return convert_dict_to_list(value)
        return convert_subitems_dict(value)
    elif isinstance(value, list):
        return convert_list(value)
    return value


def convert_dict_to_list(dct):
    if is_array(dct):
        lst = [None] * dct['count']
        for index, value in dct.items():
            if index == 'count':
                continue
            key = next(iter(value))
            lst[int(index)] = convert_value(value[key])
        return lst
    raise ValueError('need a proper dict')


def convert_subitems_dict(dct):
    d = {}
    if '0' in dct and 'count' not in dct and len(dct['0']) == 1:
        subkey = next(iter(dct['0']))
        subvalue = dct.pop('0')[subkey]
        d[subkey] = convert_value(subvalue)
    for key, value in dct.items():
        d[key] = convert_value(value)
    return d


def convert_list(lst):
    value_dicts = []
    l = []
    # base case is no items in list
    for item in lst:
        value = convert_value(item)
        if value:
            if isinstance(value, dict):
                value_dicts.append(value)
            else:
                l.append(value)
    if value_dicts and l:
        raise ValueError('shouldnt happen')
    if value_dicts:
        if all(len(d.keys()) == 1 for d in value_dicts):
            for d in value_dicts:
                key = next(iter(d))
                l.append(d.pop(key))
            return l
        else:
            all_d = {}
            for d in value_dicts:
                all_d.update(d)
            return all_d
    if l:
        return l
    return None


################################################################################


def get_game_id(_type):
    response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/game/{}?format=json'.format(_type))
    return convert_value(response.json())['fantasy_content']['game']['game_id']


def get_league_key(_type, league_id):
    return "{game_id}.l.{league_id}".format(game_id=get_game_id(_type), league_id=league_id)


def get_teams(league_key):
    response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/teams?format=json'.format(league_key=league_key))
    teams = {}
    for team in convert_value(response.json())['fantasy_content']['league']['teams']:
        teams[team['team_key']] = team['managers'][0]['nickname']
    return teams


def get_stat_definitions(league_key):
    response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings?format=json'.format(league_key=league_key))
    stat_definitions = {}
    for stat in convert_value(response.json())['fantasy_content']['league']['settings']['stat_categories']['stats']:
        stat_definitions[stat['stat_id']] = {
            'name': stat['name'],
            'abbrev': stat['display_name'],
            'position_type': stat['position_type'],
        }
    return stat_definitions


def get_modifiers(league_key):
    response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/settings?format=json'.format(league_key=league_key))
    modifiers = {}
    for s in convert_value(response.json())['fantasy_content']['league']['settings']['stat_modifiers']['stats']:
        modifiers[s['stat_id']] = Decimal(s['value'])
    return modifiers


def get_players(league_key, position):
    all_players = []
    start = 0
    count = 25
    while True:
        response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;position={position};start={start};count={count}?format=json'.format(league_key=league_key, position=position, start=start, count=count))
        value = convert_value(response.json())
        players = [player for player in value['fantasy_content']['league']['players']]
        all_players.extend(players)
        if len(players) < count:
            break
        start += count
    return all_players


def get_player_stats(stat_definitions, player_key, start_week, end_week):
    metadata = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/player/{player_key}/metadata?format=json'.format(player_key=player_key))
    metadata = convert_value(metadata.json())['fantasy_content']['player']
    position = metadata['display_position']
    team_abbr = metadata['editorial_team_abbr']
    team_name =  metadata['editorial_team_full_name']
    team_key =  metadata['editorial_team_key']
    full_name = metadata['name']['full']
    bye_week = metadata['bye_weeks']['week']

    weekly_player_stats = []
    for week in range(start_week, end_week+1):
        response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/player/{player_key}/stats;type=week;week={week}?format=json'.format(player_key=player_key, week=week))
        weekly_player_stats.append(convert_value(response.json())['fantasy_content']['player']['player_stats']['stats'])
    all_rows = []
    week = start_week
    for player_stats in weekly_player_stats:
        row = {
            'Week': week,
            'Position': position,
            'Team Abbr': team_abbr,
            'Team Name': team_name,
            'Team Key': team_key,
            'Name': full_name,
            'Bye Week': bye_week,
        }
        week += 1
        for stat in player_stats:
            if stat['stat_id'] in stat_definitions:
                row[stat_definitions[stat['stat_id']]['abbrev']] = stat['value']
        all_rows.append(row)
    return pd.DataFrame(all_rows)



def get_scores(league_key, week):
    teams = get_teams(league_key)
    scores = {}
    response = oauth.session.get("https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/scoreboard;week={week}?format=json".format(league_key=league_key, week=week))
    for m in convert_value(response.json())['fantasy_content']['league']['scoreboard']['matchups']:
        for team in m['teams']:
            scores[teams[team['team_key']]] = Decimal(team['team_points']['total'])
    return scores


def print_scores(league_key, week):
    scores = get_scores(league_key, week)
    order = [
      'Larry',
      'Richard',
      'Aditya',
      'Kevin Heh',
      'daniel',
      'Fdsf',
      'Walter White',
      'Chinmay',
      'Justin',
      'jared',
    ]
    for name in order:
        print(scores[name])


################################################################################

_type = 'nfl'
league_id = 52839
league_key = get_league_key(_type, league_id)

# print_json(get_stat_definitions(league_key))
# get_players(league_key, 'QB')

# defenses = get_players(league_key, 'DEF')
players = get_players(league_key, 'RB')
stat_definitions = get_stat_definitions(league_key)
# print_json(stat_definitions)
# print_json(players[0])
print(get_player_stats(stat_definitions, players[0]['player_key'], 1, 9).to_csv(sep='\t'))

# print_scores(league_key, 9)


# response = oauth.session.get('https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/players;position={position}?format=json'.format(league_key=league_key, position='DEF'))
# print_json(convert_value(response.json()))
