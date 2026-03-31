"""
Script thay thế comment trong file Solidity (.sol) bằng khoảng trắng
Hỗ trợ 3 loại comment:
  1. Single-line comment: // ...
  2. Multi-line comment: /* ... */
  3. NatSpec/Doc comment: /** ... */

Mục tiêu: Bảo toàn số thứ tự dòng (line numbers) và cấu trúc của file gốc.
"""

import os
import sys
import argparse


def remove_solidity_comments(source_code: str) -> str:
    """
    Loại bỏ tất cả comment khỏi mã nguồn Solidity nhưng giữ nguyên số dòng.
    Thay thế các ký tự comment bằng khoảng trắng (space), giữ nguyên tab và xuống dòng.
    """
    result = []
    i = 0
    length = len(source_code)

    while i < length:
        # --- Trạng thái: Trong chuỗi string ---
        if source_code[i] in ('"', "'"):
            quote_char = source_code[i]
            result.append(source_code[i])
            i += 1
            # Duyệt đến hết chuỗi string, xử lý escape character
            while i < length and source_code[i] != quote_char:
                if source_code[i] == '\\' and i + 1 < length:
                    # Escape character → giữ cả 2 ký tự
                    result.append(source_code[i])
                    result.append(source_code[i + 1])
                    i += 2
                else:
                    result.append(source_code[i])
                    i += 1
            # Thêm ký tự đóng chuỗi
            if i < length:
                result.append(source_code[i])
                i += 1

        # --- Trạng thái: Single-line comment (//) ---
        elif source_code[i] == '/' and i + 1 < length and source_code[i + 1] == '/':
            # Thay thế // bằng 2 khoảng trắng
            result.append(' ')
            result.append(' ')
            i += 2
            # Thay thế các ký tự tiếp theo bằng khoảng trắng cho đến hết dòng
            while i < length and source_code[i] != '\n':
                result.append(' ')
                i += 1
            # Giữ lại ký tự xuống dòng (sẽ được xử lý ở vòng lặp tiếp theo)

        # --- Trạng thái: Multi-line comment (/* ... */ hoặc /** ... */) ---
        elif source_code[i] == '/' and i + 1 < length and source_code[i + 1] == '*':
            # Thay thế /* bằng 2 khoảng trắng
            result.append(' ')
            result.append(' ')
            i += 2
            # Duyệt cho đến khi gặp */
            while i < length:
                if source_code[i] == '*' and i + 1 < length and source_code[i + 1] == '/':
                    # Thay thế */ bằng 2 khoảng trắng
                    result.append(' ')
                    result.append(' ')
                    i += 2
                    break
                
                # Nếu là xuống dòng, phải giữ nguyên để bảo toàn số dòng
                if source_code[i] == '\n':
                    result.append('\n')
                else:
                    # Các ký tự khác trong comment thay bằng khoảng trắng
                    result.append(' ')
                i += 1

        # --- Trạng thái: Ký tự bình thường ---
        else:
            result.append(source_code[i])
            i += 1

    return ''.join(result)


def process_file(input_path: str, output_path: str) -> dict:
    """
    Xử lý 1 file Solidity: đọc, thay thế comment, ghi ra file mới.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        original = f.read()

    cleaned = remove_solidity_comments(original)

    # Tạo thư mục đầu ra nếu chưa tồn tại
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned)

    # Kiểm tra số dòng để đảm bảo tính đúng đắn
    original_lines = original.count('\n') + (0 if original.endswith('\n') else 1)
    cleaned_lines = cleaned.count('\n') + (0 if cleaned.endswith('\n') else 1)

    return {
        'input': input_path,
        'output': output_path,
        'original_lines': original_lines,
        'cleaned_lines': cleaned_lines,
        'line_match': original_lines == cleaned_lines,
        'original_size': len(original),
        'cleaned_size': len(cleaned),
    }


def process_directory(input_dir: str, output_dir: str) -> list:
    """
    Xử lý tất cả file .sol trong thư mục (đệ quy).
    """
    results = []

    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            if filename.endswith('.sol'):
                input_path = os.path.join(root, filename)
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path)

                try:
                    stats = process_file(input_path, output_path)
                    results.append(stats)
                    status = "✓" if stats['line_match'] else "⚠"
                    print(f"  {status} {rel_path}: {stats['original_lines']} dòng (khớp: {stats['line_match']})")
                except Exception as e:
                    print(f"  ✗ {rel_path}: LỖI - {e}")
                    results.append({'input': input_path, 'error': str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Thay thế comment trong file Solidity (.sol) bằng khoảng trắng (bảo toàn số dòng)'
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Đường dẫn file .sol hoặc thư mục chứa file .sol')
    parser.add_argument('-o', '--output', required=True,
                        help='Đường dẫn file hoặc thư mục đầu ra')

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    if os.path.isfile(input_path):
        print(f"Đang xử lý file: {input_path}")
        stats = process_file(input_path, output_path)
        print(f"\n═══ KẾT QUẢ ═══")
        print(f"  Số dòng gốc:    {stats['original_lines']}")
        print(f"  Số dòng mới:     {stats['cleaned_lines']}")
        print(f"  Khớp số dòng:    {'CÓ' if stats['line_match'] else 'KHÔNG'}")
        print(f"  Lưu tại:         {output_path}")

    elif os.path.isdir(input_path):
        print(f"Đang xử lý thư mục: {input_path}")
        print(f"Đầu ra:             {output_path}")
        print(f"{'─' * 60}")
        results = process_directory(input_path, output_path)

        success = [r for r in results if 'error' not in r]
        errors = [r for r in results if 'error' in r]
        mismatched = [r for r in success if not r['line_match']]

        print(f"\n{'═' * 60}")
        print(f"═══ THỐNG KÊ TỔNG ═══")
        print(f"  Tổng file xử lý:       {len(success)}")
        print(f"  Tổng file lỗi:         {len(errors)}")
        print(f"  Số file lệch dòng:     {len(mismatched)}")

    else:
        print(f"Lỗi: Không tìm thấy '{input_path}'")
        sys.exit(1)


if __name__ == '__main__':
    main()
