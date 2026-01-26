import random

# --- BO'LIM 1: G'OLIBNI ANIQLASH ---

def check_winner(board, size, win_len):
    """
    Funksiya 1.1.1: G'olibni qidirish algoritmi.
    Tic-Tac-Toe mantiig'i bo'yicha qator, ustun va diagonallarni tekshiradi.
    """
    # 1. Qatorlar bo'yicha tekshirish
    for r in range(size):
        for c in range(size - win_len + 1):
            window = [board[r][c + i] for i in range(win_len)]
            # Agar barcha belgilar bir xil bo'lsa va bo'sh yoki muzlatilgan bo'lmasa
            if len(set(window)) == 1 and window[0] not in [' ', '✅']:
                return window[0]

    # 2. Ustunlar bo'yicha tekshirish
    for r in range(size - win_len + 1):
        for c in range(size):
            window = [board[r + i][c] for i in range(win_len)]
            if len(set(window)) == 1 and window[0] not in [' ', '✅']:
                return window[0]

    # 3. Diagonallar bo'yicha tekshirish
    for r in range(size - win_len + 1):
        for c in range(size - win_len + 1):
            # Asosiy diagonal \
            diag1 = [board[r + i][c + i] for i in range(win_len)]
            if len(set(diag1)) == 1 and diag1[0] not in [' ', '✅']:
                return diag1[0]
            
            # Teskari diagonal /
            diag2 = [board[r + i][c + win_len - 1 - i] for i in range(win_len)]
            if len(set(diag2)) == 1 and diag2[0] not in [' ', '✅']:
                return diag2[0]

    # 4. Durrang tekshiruvi (Barcha kataklar to'lgan bo'lsa)
    if all(cell != ' ' for row in board for cell in row):
        return 'Draw'
    
    return None

def get_empty_cells(board, size):
    """Funksiya 1.2.1: Barcha bo'sh kataklar koordinatalarini qaytaradi."""
    return [(r, c) for r in range(size) for c in range(size) if board[r][c] == ' ']

# --- BO'LIM 2: ROBOT INTELLEKTI (MEDIUM AI) ---

def get_robot_move(board, size, win_len, robot_symbol):
    """
    Robot mantiig'i:
    1. Yutish imkonini qidiradi (G'alaba yurishi).
    2. Raqibni bloklaydi (Barcha raqib skinlarini hisobga oladi).
    3. Strategik markazni egallashga harakat qiladi.
    4. Tasodifiy yurish.
    """
    empty_cells = get_empty_cells(board, size)
    if not empty_cells:
        return None

    # 2.1.1. O'zining g'alaba yurishini tekshirish
    for r, c in empty_cells:
        board[r][c] = robot_symbol
        if check_winner(board, size, win_len) == robot_symbol:
            board[r][c] = ' ' 
            return r, c
        board[r][c] = ' '

    # 2.1.2. Raqiblarni bloklash (Multiplayer/Battle rejimi uchun)
    opponent_symbols = set()
    for row in board:
        for cell in row:
            if cell not in [' ', '✅', robot_symbol]:
                opponent_symbols.add(cell)

    for opp in opponent_symbols:
        for r, c in empty_cells:
            board[r][c] = opp
            if check_winner(board, size, win_len) == opp:
                board[r][c] = ' '
                return r, c
            board[r][c] = ' '

    # 2.1.3. Markaziy katak strategiyasi
    center = size // 2
    if (center, center) in empty_cells:
        return center, center

    # 2.1.4. Tasodifiy yurish
    return random.choice(empty_cells)

# --- BO'LIM 3: O'YIN HOLATI ---

def is_game_over(board, active_players_count):
    """
    Funksiya 3.1.1: O'yin tugash shartlarini tekshiradi.
    Faqat bitta o'yinchi qolganda yoki doska to'lganda o'yin tugaydi.
    """
    if active_players_count <= 1:
        return True
    
    if all(cell != ' ' for row in board for cell in row):
        return True
        
    return False