"""Move-file evaluator Lambda.

Invoked asynchronously by the confirm handler once a submission reaches
CONFIRMED. Reads the uploaded move file from S3, validates every move with a
dependency-free chess engine, records DONE/FAILED in DynamoDB, and emails the
result (the winner on DONE, the specific reason on FAILED).
"""
import boto3
import os
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from botocore.exceptions import ClientError

from board_image import render_board_png

table = boto3.resource('dynamodb').Table(os.environ['SUBMISSIONS_TABLE'])
s3 = boto3.client('s3')
ses = boto3.client('ses')

# --- chess engine ------------------------------------------------
FILES = 'abcdefgh'
PIECE_NAMES = {'P': 'pawn', 'N': 'knight', 'B': 'bishop', 'R': 'rook', 'Q': 'queen', 'K': 'king'}


def parse_square(sq):
    sq = sq.strip().lower()
    if len(sq) != 2 or sq[0] not in FILES or sq[1] not in '12345678':
        return None
    return (FILES.index(sq[0]), int(sq[1]) - 1)


def initial_board():
    board = [[None] * 8 for _ in range(8)]
    back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
    for c in range(8):
        board[0][c] = ('w', back[c])
        board[1][c] = ('w', 'P')
        board[6][c] = ('b', 'P')
        board[7][c] = ('b', back[c])
    return board


def path_clear(board, c0, r0, c1, r1):
    dc = (c1 > c0) - (c1 < c0)
    dr = (r1 > r0) - (r1 < r0)
    c, r = c0 + dc, r0 + dr
    while (c, r) != (c1, r1):
        if board[r][c] is not None:
            return False
        c += dc
        r += dr
    return True


def pseudo_legal(board, c0, r0, c1, r1, color):
    piece = board[r0][c0]
    if piece is None or piece[0] != color or (c0, r0) == (c1, r1):
        return False
    target = board[r1][c1]
    if target is not None and target[0] == color:
        return False
    kind = piece[1]
    dc, dr = c1 - c0, r1 - r0
    if kind == 'P':
        direction = 1 if color == 'w' else -1
        start_rank = 1 if color == 'w' else 6
        if dc == 0 and dr == direction and target is None:
            return True
        if (dc == 0 and dr == 2 * direction and r0 == start_rank
                and target is None and board[r0 + direction][c0] is None):
            return True
        if abs(dc) == 1 and dr == direction and target is not None:
            return True
        return False
    if kind == 'N':
        return (abs(dc), abs(dr)) in ((1, 2), (2, 1))
    if kind == 'B':
        return abs(dc) == abs(dr) and path_clear(board, c0, r0, c1, r1)
    if kind == 'R':
        return (dc == 0 or dr == 0) and path_clear(board, c0, r0, c1, r1)
    if kind == 'Q':
        return (dc == 0 or dr == 0 or abs(dc) == abs(dr)) and path_clear(board, c0, r0, c1, r1)
    if kind == 'K':
        return max(abs(dc), abs(dr)) == 1
    return False


def find_king(board, color):
    for r in range(8):
        for c in range(8):
            if board[r][c] == (color, 'K'):
                return (c, r)
    return None


def is_attacked(board, c, r, by_color):
    for rr in range(8):
        for cc in range(8):
            p = board[rr][cc]
            if p and p[0] == by_color and pseudo_legal(board, cc, rr, c, r, by_color):
                return True
    return False


def in_check(board, color):
    k = find_king(board, color)
    if k is None:
        return False
    return is_attacked(board, k[0], k[1], 'b' if color == 'w' else 'w')


def make_move(board, c0, r0, c1, r1):
    nb = [row[:] for row in board]
    nb[r1][c1] = nb[r0][c0]
    nb[r0][c0] = None
    return nb


def has_any_legal_move(board, color):
    for r0 in range(8):
        for c0 in range(8):
            p = board[r0][c0]
            if not p or p[0] != color:
                continue
            for r1 in range(8):
                for c1 in range(8):
                    if pseudo_legal(board, c0, r0, c1, r1, color):
                        if not in_check(make_move(board, c0, r0, c1, r1), color):
                            return True
    return False


def move_error(board, c0, r0, c1, r1, color, src, dst):
    piece = board[r0][c0]
    if piece is None:
        return 'the start square {} is empty'.format(src)
    if piece[0] != color:
        side = 'White' if color == 'w' else 'Black'
        return 'it is {} to move, but {} holds a {} piece'.format(
            side, src, 'white' if piece[0] == 'w' else 'black')
    target = board[r1][c1]
    if target is not None and target[0] == color:
        return 'the {} on {} cannot capture your own piece on {}'.format(
            PIECE_NAMES[piece[1]], src, dst)
    if not pseudo_legal(board, c0, r0, c1, r1, color):
        kind = piece[1]
        dc, dr = c1 - c0, r1 - r0
        geom_ok = {'B': abs(dc) == abs(dr), 'R': dc == 0 or dr == 0,
                   'Q': dc == 0 or dr == 0 or abs(dc) == abs(dr)}.get(kind)
        if geom_ok and not path_clear(board, c0, r0, c1, r1):
            return 'the {} on {} is blocked on its way to {}'.format(PIECE_NAMES[kind], src, dst)
        return 'the {} on {} cannot move to {}'.format(PIECE_NAMES[kind], src, dst)
    if in_check(make_move(board, c0, r0, c1, r1), color):
        return 'moving {} to {} would leave your king in check'.format(src, dst)
    return None


def validate_game(text):
    board = initial_board()
    color = 'w'
    winner = None
    ended = None
    played = 0
    move_no = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        move_no += 1
        if ended is not None:
            return {'valid': False, 'winner': None, 'moves': played, 'board': board,
                    'reason': 'move {} ({}) was played after the game already ended in {}'.format(move_no, line, ended)}
        parts = line.split()
        if len(parts) != 2:
            return {'valid': False, 'winner': None, 'moves': played, 'board': board,
                    'reason': 'move {} ("{}") is not in "<from> <to>" format'.format(move_no, line)}
        src_txt, dst_txt = parts[0].lower(), parts[1].lower()
        src, dst = parse_square(src_txt), parse_square(dst_txt)
        if src is None or dst is None:
            return {'valid': False, 'winner': None, 'moves': played, 'board': board,
                    'reason': 'move {} ("{}") uses a square outside a1-h8'.format(move_no, line)}
        c0, r0 = src
        c1, r1 = dst
        err = move_error(board, c0, r0, c1, r1, color, src_txt, dst_txt)
        if err is not None:
            return {'valid': False, 'winner': None, 'moves': played, 'board': board,
                    'reason': 'move {} ({} {}) is illegal: {}'.format(move_no, src_txt, dst_txt, err)}
        board = make_move(board, c0, r0, c1, r1)
        played += 1
        opponent = 'b' if color == 'w' else 'w'
        if not has_any_legal_move(board, opponent):
            if in_check(board, opponent):
                winner = color
                ended = 'checkmate'
            else:
                ended = 'stalemate'
        color = opponent
    return {'valid': True, 'winner': winner, 'moves': played, 'reason': None,
            'ended': ended, 'board': board}


# --- handler -----------------------------------------------------
def _send(to, subject, body, image=None):
    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = os.environ['EMAIL_FROM']
    msg['To'] = to
    msg.attach(MIMEText(body, 'plain', 'us-ascii'))
    if image is not None:
        part = MIMEImage(image, _subtype='png')
        part.add_header('Content-Disposition', 'attachment', filename='end_position.png')
        msg.attach(part)
    ses.send_raw_email(
        Source=os.environ['EMAIL_FROM'], Destinations=[to],
        RawMessage={'Data': msg.as_string()})


def handler(event, context):
    submission_id = (event or {}).get('submissionId')
    if not submission_id:
        return {'status': 'ERROR'}
    item = table.get_item(Key={'submissionId': submission_id}).get('Item')
    if not item or item.get('status') != 'CONFIRMED':
        return {'status': item.get('status', 'ERROR') if item else 'ERROR'}
    try:
        obj = s3.get_object(Bucket=os.environ['UPLOAD_BUCKET'], Key=item['objectKey'])
        text = obj['Body'].read().decode('utf-8', 'replace')
    except Exception:
        table.update_item(
            Key={'submissionId': submission_id},
            UpdateExpression='SET #s = :err',
            ConditionExpression='#s = :confirmed',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':err': 'ERROR', ':confirmed': 'CONFIRMED'})
        return {'status': 'ERROR'}

    result = validate_game(text)
    new_status = 'DONE' if result['valid'] else 'FAILED'
    winner = result['winner']
    winner_label = {'w': 'white', 'b': 'black'}.get(winner)
    try:
        table.update_item(
            Key={'submissionId': submission_id},
            UpdateExpression='SET #s = :new, resultAt = :now, movesValidated = :moves, '
                             'gameWinner = :winner, failureReason = :reason, expiresAt = :expires',
            ConditionExpression='#s = :confirmed',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':new': new_status, ':now': int(time.time()),
                ':moves': result['moves'],
                ':winner': winner_label or 'none',
                ':reason': result['reason'] or 'none',
                ':confirmed': 'CONFIRMED',
                ':expires': int(time.time()) + 30 * 24 * 3600})
    except ClientError as error:
        if error.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {'status': 'ALREADY_PROCESSED'}
        raise

    try:
        image = render_board_png(result['board'])
    except Exception:
        image = None  # never drop the result email over a rendering error

    to = item['email']
    if new_status == 'DONE':
        if winner_label:
            outcome = '{} wins by checkmate.'.format(winner_label.capitalize())
        else:
            outcome = 'There is no winner: no checkmate was reached (the game is unfinished or drawn).'
        body = ('Good news - your chess game file is valid.\n\n'
                'Moves validated: {}\n'
                'Result: {}\n\n'
                'The attached image shows the final position.\n'.format(result['moves'], outcome))
        _send(to, 'Your Chess Move Validator result: DONE', body, image)
    else:
        body = ('Your chess game file is invalid, so no winner can be declared.\n\n'
                'Reason: {}\n\n'
                'The attached image shows the position reached before the problem move.\n'.format(result['reason']))
        _send(to, 'Your Chess Move Validator result: FAILED', body, image)
    return {'status': new_status, 'winner': winner_label}
