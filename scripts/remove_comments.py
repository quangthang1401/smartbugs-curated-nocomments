"""
Script loại bỏ comment trong file Solidity (.sol)
Hỗ trợ 3 loại comment:
  1. Single-line comment: // ...
  2. Multi-line comment: /* ... */
  3. NatSpec/Doc comment: /** ... */

Lưu ý: Script xử lý đúng các trường hợp:
  - Chuỗi string chứa ký tự // hoặc /* (không phải comment thật)
  - Comment lồng nhau
  - Dòng trống liên tiếp sau khi xóa comment
"""

import re
import os
import sys
import argparse


def remove_solidity_comments(source_code: str, collapse_blank_lines: bool = True) -> str:
    """
    Loại bỏ tất cả comment khỏi mã nguồn Solidity.

    Thuật toán: Duyệt từng ký tự, phân biệt trạng thái:
      - Trong chuỗi string (đơn '' hoặc kép "")  → giữ nguyên
      - Gặp // → bỏ đến hết dòng (single-line comment)
      - Gặp /* → bỏ đến khi gặp */ (multi-line/doc comment)
      - Còn lại → giữ nguyên

    Args:
        source_code: Mã nguồn Solidity gốc
        collapse_blank_lines: Nếu True, gộp các dòng trống liên tiếp thành 1 dòng trống

    Returns:
        Mã nguồn đã loại bỏ comment
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
            # Bỏ qua tất cả cho đến hết dòng
            i += 2
            while i < length and source_code[i] != '\n':
                i += 1
            # Giữ lại ký tự xuống dòng
            # (không tăng i, sẽ được xử lý ở vòng lặp tiếp theo)

        # --- Trạng thái: Multi-line comment (/* ... */ hoặc /** ... */) ---
        elif source_code[i] == '/' and i + 1 < length and source_code[i + 1] == '*':
            i += 2  # Bỏ qua /*
            # Duyệt cho đến khi gặp */
            while i < length:
                if source_code[i] == '*' and i + 1 < length and source_code[i + 1] == '/':
                    i += 2  # Bỏ qua */
                    break
                i += 1

        # --- Trạng thái: Ký tự bình thường ---
        else:
            result.append(source_code[i])
            i += 1

    cleaned = ''.join(result)

    if collapse_blank_lines:
        # Xóa trailing whitespace trên mỗi dòng
        lines = cleaned.split('\n')
        lines = [line.rstrip() for line in lines]

        # Gộp nhiều dòng trống liên tiếp thành 1
        collapsed = []
        prev_blank = False
        for line in lines:
            if line.strip() == '':
                if not prev_blank:
                    collapsed.append('')
                prev_blank = True
            else:
                collapsed.append(line)
                prev_blank = False

        # Xóa dòng trống đầu file
        while collapsed and collapsed[0].strip() == '':
            collapsed.pop(0)
        # Xóa dòng trống cuối file (giữ 1 newline cuối)
        while collapsed and collapsed[-1].strip() == '':
            collapsed.pop()

        cleaned = '\n'.join(collapsed) + '\n'

    return cleaned


def process_file(input_path: str, output_path: str, collapse_blank_lines: bool = True) -> dict:
    """
    Xử lý 1 file Solidity: đọc, loại bỏ comment, ghi ra file mới.

    Args:
        input_path: Đường dẫn file .sol gốc
        output_path: Đường dẫn file .sol đầu ra (đã loại bỏ comment)
        collapse_blank_lines: Gộp dòng trống liên tiếp

    Returns:
        Dict chứa thông tin thống kê
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        original = f.read()

    cleaned = remove_solidity_comments(original, collapse_blank_lines)

    # Tạo thư mục đầu ra nếu chưa tồn tại
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(cleaned)

    original_lines = len(original.split('\n'))
    cleaned_lines = len(cleaned.split('\n'))
    removed_lines = original_lines - cleaned_lines

    return {
        'input': input_path,
        'output': output_path,
        'original_lines': original_lines,
        'cleaned_lines': cleaned_lines,
        'removed_lines': removed_lines,
        'original_size': len(original),
        'cleaned_size': len(cleaned),
    }


def process_directory(input_dir: str, output_dir: str, collapse_blank_lines: bool = True) -> list:
    """
    Xử lý tất cả file .sol trong thư mục (đệ quy), lưu kết quả vào output_dir
    giữ nguyên cấu trúc thư mục.

    Args:
        input_dir: Thư mục chứa file .sol gốc
        output_dir: Thư mục đầu ra
        collapse_blank_lines: Gộp dòng trống liên tiếp

    Returns:
        List chứa thông tin thống kê cho từng file
    """
    results = []

    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            if filename.endswith('.sol'):
                input_path = os.path.join(root, filename)
                # Tính đường dẫn tương đối để giữ cấu trúc thư mục
                rel_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, rel_path)

                try:
                    stats = process_file(input_path, output_path, collapse_blank_lines)
                    results.append(stats)
                    print(f"  ✓ {rel_path}: {stats['original_lines']} → {stats['cleaned_lines']} dòng "
                          f"(loại bỏ {stats['removed_lines']} dòng)")
                except Exception as e:
                    print(f"  ✗ {rel_path}: LỖI - {e}")
                    results.append({'input': input_path, 'error': str(e)})

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Loại bỏ comment trong file Solidity (.sol)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ sử dụng:
  # Xử lý 1 file
  python remove_comments.py -i input.sol -o output.sol

  # Xử lý cả thư mục (đệ quy)
  python remove_comments.py -i dataset/ -o dataset_no_comments/

  # Không gộp dòng trống
  python remove_comments.py -i dataset/ -o output/ --keep-blank-lines
        """
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Đường dẫn file .sol hoặc thư mục chứa file .sol')
    parser.add_argument('-o', '--output', required=True,
                        help='Đường dẫn file hoặc thư mục đầu ra')
    parser.add_argument('--keep-blank-lines', action='store_true',
                        help='Không gộp các dòng trống liên tiếp')

    args = parser.parse_args()
    collapse = not args.keep_blank_lines

    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    if os.path.isfile(input_path):
        # Xử lý 1 file
        print(f"Đang xử lý file: {input_path}")
        stats = process_file(input_path, output_path, collapse)
        print(f"\n═══ KẾT QUẢ ═══")
        print(f"  File gốc:       {stats['original_lines']} dòng ({stats['original_size']} bytes)")
        print(f"  File đã xử lý:  {stats['cleaned_lines']} dòng ({stats['cleaned_size']} bytes)")
        print(f"  Đã loại bỏ:     {stats['removed_lines']} dòng")
        print(f"  Lưu tại:        {output_path}")

    elif os.path.isdir(input_path):
        # Xử lý thư mục
        print(f"Đang xử lý thư mục: {input_path}")
        print(f"Đầu ra:             {output_path}")
        print(f"{'─' * 60}")
        results = process_directory(input_path, output_path, collapse)

        # Thống kê tổng
        success = [r for r in results if 'error' not in r]
        errors = [r for r in results if 'error' in r]
        total_original = sum(r['original_lines'] for r in success)
        total_cleaned = sum(r['cleaned_lines'] for r in success)
        total_removed = sum(r['removed_lines'] for r in success)

        print(f"\n{'═' * 60}")
        print(f"═══ THỐNG KÊ TỔNG ═══")
        print(f"  Tổng file xử lý:       {len(success)}")
        print(f"  Tổng file lỗi:         {len(errors)}")
        print(f"  Tổng dòng gốc:         {total_original}")
        print(f"  Tổng dòng sau xử lý:   {total_cleaned}")
        print(f"  Tổng dòng đã loại bỏ:  {total_removed}")
        if total_original > 0:
            pct = (total_removed / total_original) * 100
            print(f"  Tỷ lệ giảm:            {pct:.1f}%")

    else:
        print(f"Lỗi: Không tìm thấy '{input_path}'")
        sys.exit(1)


if __name__ == '__main__':
    main()
