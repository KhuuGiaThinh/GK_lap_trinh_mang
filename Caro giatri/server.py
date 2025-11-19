from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import random
import copy
import threading

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

rooms = {}
waiting_player = None
BOARD_SIZE = 16
lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')


def find_five_in_a_row(board, symbol):
    """Trả về danh sách 5 ô tạo thành chiến thắng nếu có, ngược lại trả về None."""
    n = len(board)
    # ngang
    for i in range(n):
        for j in range(n - 4):
            seq = [(i, j + k) for k in range(5)]
            if all(board[x][y] == symbol for x, y in seq):
                return seq
    # dọc
    for j in range(n):
        for i in range(n - 4):
            seq = [(i + k, j) for k in range(5)]
            if all(board[x][y] == symbol for x, y in seq):
                return seq
    # chéo chính
    for i in range(n - 4):
        for j in range(n - 4):
            seq = [(i + k, j + k) for k in range(5)]
            if all(board[x][y] == symbol for x, y in seq):
                return seq
    # chéo phụ
    for i in range(4, n):
        for j in range(n - 4):
            seq = [(i - k, j + k) for k in range(5)]
            if all(board[x][y] == symbol for x, y in seq):
                return seq
    return None


def find_winning_move(board, symbol):
    """Tìm 1 nước đi mà symbol đặt vào sẽ thắng — trả (r,c) hoặc None."""
    n = len(board)
    for i in range(n):
        for j in range(n):
            if board[i][j] == '':
                board_copy = copy.deepcopy(board)
                board_copy[i][j] = symbol
                if find_five_in_a_row(board_copy, symbol):
                    return (i, j)
    return None


def ai_move(board):
    """AI cải tiến:
       1) nếu AI có nước thắng -> đánh
       2) nếu người chơi có nước thắng -> chặn
       3) nếu người đang có chuỗi 4 hoặc 3 (threat) -> chặn
       4) chọn ô gần ô người chơi
       5) fallback random
    """
    empties = [(i, j) for i in range(BOARD_SIZE) for j in range(BOARD_SIZE) if board[i][j] == '']
    if not empties:
        return None

    # 1) AI thắng ngay
    win_move = find_winning_move(board, 'O')
    if win_move:
        return win_move

    # 2) Chặn người thắng
    block_move = find_winning_move(board, 'X')
    if block_move:
        return block_move

    # 3) Chặn threat 4 hoặc 3
    for threat in (4, 3):
        for i, j in empties:
            board[i][j] = 'X'
            max_len = 0
            for dx, dy in [(1, 0), (0, 1), (1, 1), (1, -1)]:
                cnt = 1
                x, y = i + dx, j + dy
                while 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and board[x][y] == 'X':
                    cnt += 1
                    x += dx
                    y += dy
                x, y = i - dx, j - dy
                while 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and board[x][y] == 'X':
                    cnt += 1
                    x -= dx
                    y -= dy
                max_len = max(max_len, cnt)
            board[i][j] = ''
            if max_len >= threat:
                return (i, j)

    # 4) Ưu tiên ô gần người chơi
    human_cells = [(i, j) for i in range(BOARD_SIZE) for j in range(BOARD_SIZE) if board[i][j] == 'X']
    nearby = []
    if human_cells:
        for hx, hy in human_cells:
            for i in range(max(0, hx - 2), min(BOARD_SIZE, hx + 3)):
                for j in range(max(0, hy - 2), min(BOARD_SIZE, hy + 3)):
                    if board[i][j] == '':
                        nearby.append((i, j))
    if nearby:
        freq = {}
        for cell in nearby:
            freq[cell] = freq.get(cell, 0) + 1
        sorted_cells = sorted(freq.items(), key=lambda x: -x[1])
        return sorted_cells[0][0]

    # 5) fallback random
    return random.choice(empties)


@socketio.on('connect')
def on_connect():
    emit('connected', {'sid': request.sid})


@socketio.on('find_room')
def handle_find_room(data):
    global waiting_player
    sid = request.sid
    solo = data.get('solo', False)

    if solo:
        room_id = str(random.randint(1000, 9999))
        with lock:
            rooms[room_id] = {
                'board': [[''] * BOARD_SIZE for _ in range(BOARD_SIZE)],
                'players': {sid: 'X', 'AI': 'O'},
                'turn': 'X',
                'finished': False,
                'solo': True
            }
        join_room(room_id)
        emit('room_joined', {'room': room_id, 'symbol': 'X'}, to=sid)
        emit('start_game', {'turn': 'X'}, room=room_id)
        return

    # multiplayer
    with lock:
        if waiting_player is None:
            waiting_player = sid
            emit('waiting', {'msg': 'Đang tìm đối thủ...'}, to=sid)
            return
        else:
            opponent = waiting_player
            waiting_player = None
            room_id = str(random.randint(1000, 9999))
            rooms[room_id] = {
                'board': [[''] * BOARD_SIZE for _ in range(BOARD_SIZE)],
                'players': {opponent: 'X', sid: 'O'},
                'turn': 'X',
                'finished': False,
                'solo': False
            }
    try:
        join_room(room_id, sid=opponent)
    except Exception:
        pass
    try:
        join_room(room_id, sid=sid)
    except Exception:
        pass
    emit('room_joined', {'room': room_id, 'symbol': 'X'}, to=opponent)
    emit('room_joined', {'room': room_id, 'symbol': 'O'}, to=sid)
    emit('start_game', {'turn': 'X'}, room=room_id)


@socketio.on('make_move')
def handle_make_move(data):
    sid = request.sid
    room_id = data.get('room')
    try:
        row = int(data.get('row'))
        col = int(data.get('col'))
    except Exception:
        emit('error', {'msg': 'Tọa độ không hợp lệ'}, to=sid)
        return

    with lock:
        if room_id not in rooms:
            emit('error', {'msg': 'Phòng không tồn tại'}, to=sid)
            return

        state = rooms[room_id]
        board = state['board']
        if state['finished']:
            return

        symbol = state['players'].get(sid)
        if not symbol or state['turn'] != symbol:
            return

        if board[row][col] != '':
            return

        board[row][col] = symbol

        win_seq = find_five_in_a_row(board, symbol)
        if win_seq:
            state['finished'] = True
            socketio.emit('state_update', {
                'board': board,
                'turn': None,
                'finished': True,
                'winner': symbol,
                'winner_positions': win_seq
            }, room=room_id)
            return

        # hòa
        if all(all(c != '' for c in r) for r in board):
            state['finished'] = True
            socketio.emit('state_update', {
                'board': board,
                'turn': None,
                'finished': True,
                'winner': 'draw',
                'winner_positions': []
            }, room=room_id)
            return

        # đổi lượt
        state['turn'] = 'O' if symbol == 'X' else 'X'

        # solo mode -> AI
        if state.get('solo') and not state['finished'] and state['turn'] == 'O':
            ai_rc = ai_move(board)
            if ai_rc:
                ar, ac = ai_rc
                board[ar][ac] = 'O'
                ai_win = find_five_in_a_row(board, 'O')
                if ai_win:
                    state['finished'] = True
                    socketio.emit('state_update', {
                        'board': board,
                        'turn': None,
                        'finished': True,
                        'winner': 'O',
                        'winner_positions': ai_win
                    }, room=room_id)
                    return
                if all(all(c != '' for c in r) for r in board):
                    state['finished'] = True
                    socketio.emit('state_update', {
                        'board': board,
                        'turn': None,
                        'finished': True,
                        'winner': 'draw',
                        'winner_positions': []
                    }, room=room_id)
                    return
                state['turn'] = 'X'

        socketio.emit('state_update', {
            'board': board,
            'turn': state['turn'],
            'finished': state['finished'],
            'winner': None,
            'winner_positions': []
        }, room=room_id)


@socketio.on('timeout')
def handle_timeout(data):
    """Xử lý khi người chơi hết 30s => xử thua."""
    room_id = data.get('room')
    sid = request.sid
    if room_id not in rooms:
        return

    state = rooms[room_id]
    if state['finished']:
        return

    loser_symbol = state['players'].get(sid)
    if not loser_symbol:
        return

    winner_symbol = 'O' if loser_symbol == 'X' else 'X'
    state['finished'] = True

    socketio.emit('state_update', {
        'board': state['board'],
        'turn': None,
        'finished': True,
        'winner': winner_symbol,
        'winner_positions': []
    }, room=room_id)


@socketio.on('disconnect')
def handle_disconnect():
    global waiting_player
    sid = request.sid
    with lock:
        if waiting_player == sid:
            waiting_player = None

        to_remove = []
        for rid, state in list(rooms.items()):
            if sid in state['players']:
                for psid in list(state['players'].keys()):
                    if psid != sid and psid != 'AI':
                        try:
                            socketio.emit('opponent_left', {'msg': 'Đối thủ đã rời phòng'}, to=psid)
                        except Exception:
                            pass
                to_remove.append(rid)
        for rid in to_remove:
            rooms.pop(rid, None)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
