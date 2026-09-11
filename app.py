import argparse
import json
import sys
import urllib.request
from reminder.storage import Store
from reminder.bridge import PORT


def cli():
    from reminder.ai import AI
    store = Store()
    ai = AI(store)
    print('启动助手 CLI：/tasks 清单；/add 任务；/done 编号；/shelve 编号；/review 复盘；')
    print('/plan 模糊描述（确认后保存）；/clear 清空聊天；/quit 退出。其他输入进入连续聊天。')
    while True:
        try:
            text = input('\n你 > ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        try:
            if text == '/quit':
                break
            elif text == '/tasks':
                for t in store.tasks(all_pending=True):
                    print(f'{t["id"]}. {t["text"]}  {t["due"]}')
            elif text.startswith('/add '):
                store.add_tasks([text[5:]])
                print('已保存。')
            elif text.startswith('/done ') or text.startswith('/shelve '):
                command, value = text.split(maxsplit=1)
                store.update_task(int(value), status='done' if command == '/done' else 'shelved')
                print('已更新。')
            elif text.startswith('/review '):
                store.review(text[8:])
                print('复盘已保存。')
            elif text == '/clear':
                if input('清空本地聊天历史？输入 yes：') == 'yes':
                    store.clear_chat()
            elif text.startswith('/plan '):
                tasks = ai.ask(text[6:], draft=True)
                for i, task in enumerate(tasks, 1):
                    print(f'{i}. {task}')
                if input('保存这些步骤？输入 yes：') == 'yes':
                    due = input('计划日期 YYYY-MM-DD（回车表示随时）：').strip()
                    store.add_tasks(tasks, due)
                    print('已保存。')
            elif text.startswith('/'):
                print('未知命令。')
            else:
                print('助手 > ' + ai.ask(text))
        except Exception as error:
            print('未完成：' + str(error))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', nargs='?', choices=['gui', 'cli'], default='gui')
    parser.add_argument('--background', action='store_true')
    args = parser.parse_args()
    if args.mode == 'cli':
        cli()
        return
    store = Store()
    token = store.get('bridge_token')
    if token:
        try:
            request = urllib.request.Request(f'http://127.0.0.1:{PORT}/show', b'{}',
                                              {'Authorization': 'Bearer ' + token})
            with urllib.request.urlopen(request, timeout=2):
                return
        except (OSError, urllib.error.URLError):
            pass
    try:
        from reminder.gui import App
        App(background=args.background).run()
    except Exception as error:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), '启动提醒助手：启动失败', 0x10)
        raise


if __name__ == '__main__':
    main()
