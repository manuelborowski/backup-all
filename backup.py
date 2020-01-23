# backup relevant projects and data

# crontab -e
# 0 */1 * * * cd /home/aboro/projects/backup-all && python backup.py >> backup_projects.log 2>&1

# V1.0 : copy from project sqlbackup
# V1.1 : finished : dump-sql, apt-clone, duplicity and rclone
# V1.2 : apt-clone needs to be explicitly included via a flag
# V1.3 : added tracing

import sys, datetime, subprocess, os, glob, json, argparse

version = 'V1.3'


def create_and_change_dir(config, relative_path):
    absolute_path = os.path.join(config['backup_path'], relative_path)
    try:
        os.mkdir(absolute_path)
    except FileExistsError as e:
        print(f'{absolute_path}: directory already exists')
    os.chdir(absolute_path)
    return absolute_path


def init(config, arguments):
    print('Initializing...', datetime.datetime.now())
    backup_path = config['backup_path']
    if '~' in backup_path:
        backup_path = config['backup_path'] = os.path.expanduser(backup_path)
    try:
        os.mkdir(backup_path)
    except FileExistsError as e:
        print(f'{backup_path}: directory already exists')
    os.chdir(backup_path)


def export_sql(config, arguments):
    print('Export SQL...', datetime.datetime.now())
    try:
        path = create_and_change_dir(config, config['sql']['backup_path'])
        duplicity_add_path(config, path)
        now = datetime.datetime.now()
        timestamp = now.strftime('%Y-%m-%d-%H-%M')
        sql_username = config['sql']['username']
        sql_password = config['sql']['password']

        dump_file = 'backup-'
        dump_file_timestamp = f'{dump_file}{timestamp}.sql'
        print(f'>>> Dumping : {dump_file_timestamp} <<<<')
        of = open(dump_file_timestamp, 'w')
        dump = subprocess.run(f'mysqldump -u {sql_username} -p{sql_password} --skip-dump-date --all-databases'.split(), stdout=of)
        if dump.returncode == 0:
            print('Dump was OK')
            hash = subprocess.check_output(f'sha1sum {dump_file_timestamp}', shell=True).split()[0]
            dump_list = sorted(glob.glob(f'{dump_file}*'), key=os.path.getmtime)
            if len(dump_list) > 1:  # a previous sql dump file is already present
                previous_dump = dump_list[-2]
                previous_hash = subprocess.check_output(f'sha1sum {previous_dump}', shell=True).split()[0]
                if hash == previous_hash:
                    print('This dump is equal to the previous one, remove latest dump and keep previous one')
                    rm = subprocess.run(f'rm {dump_file_timestamp}'.split())
                    if rm.returncode != 0:
                        print(f'Error, could not remove {dump_file_timestamp}')
                else:
                    print('This dump has changed, remove previous dump')
                    rm = subprocess.run(f'rm {previous_dump}'.split())
                    if rm.returncode != 0:
                        print(f'Error, could not remove {previous_dump}')
        else:
            print(f'Dump was NOK : returncode {dump.returncode}')
            rm = subprocess.run(f'rm {dump_file_timestamp}'.split())
            if rm.returncode != 0:
                print(f'Error, could not remove {dump_file_timestamp}')
    except Exception as e:
        print(f"Could not dump sql : {e}")


def clone_apt(config, arguments):
    print('clone_apt...', datetime.datetime.now())
    try:
        path = create_and_change_dir(config, config['apt']['backup_path'])
        duplicity_add_path(config, path)
        clone = subprocess.run(f'apt-clone clone --with-dpkg-repack .'.split())
        if clone.returncode == 0:
            print('Clone was OK')
        else:
            print(f'Clone was NOK : returncode {clone.returncode}')
    except Exception as e:
        print(f"Could not apt-clone : {e}")


def duplicity_add_path(config, path, include=True):
    filelist = config['duplicity']['filelist']
    filelist.insert(0, f'{"+" if include else "-" } {path}')
    config['duplicity']['filelist'] = filelist


def duplicity(config, arguments):
    print('Duplicity...', datetime.datetime.now())
    try:
        path = create_and_change_dir(config, config['duplicity']['backup_path'])
        rclone_overwrite_source_path(config, path)
        source_path = config['duplicity']['source_path']
        key = config['duplicity']['key']
        include_option = ''
        for i in config['duplicity']['include']:
            include_option += f' --include {i}'
        exclude_option = ''
        for i in config['duplicity']['exclude']:
            exclude_option += f' --exclude {i}'
        file_option = ''
        for i in config['duplicity']['filelist']:
            if i[0] == '#':
                continue
            split_line = i.split(' ')
            if len(split_line) == 2:
                if split_line[0] == '-':
                    file_option += f' --exclude {split_line[1]}'
                else:
                    file_option += f' --include {split_line[1]}'
            else:
                file_option += f' --include {split_line[0]}'

        duplicity_command = f'env PASSPHRASE={key} duplicity {include_option} {exclude_option} {file_option} {source_path} file://.'
        print('duplicity command:' ,duplicity_command)
        dump = subprocess.run(duplicity_command.split())
        if dump.returncode == 0:
            print('Duplicity was OK'    )
        else:
            print(f'Duplicity was NOK : returncode {dump.returncode}')

    except Exception as e:
        print(f"Could not duplicity : {e}")


def rclone_overwrite_source_path(config, path):
    config['rclone']['source_path'] = path


def rclone_copy(config, arguments):
    source_path = config['rclone']['source_path']
    backup_path = config['rclone']['backup_path']
    rclone = subprocess.run(f'rclone copy {source_path} {backup_path}'.split())
    if rclone.returncode != 0:
        print(f'Error, could not rclone from {source_path} to {backup_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update sql database(s) and store in cloud')
    parser.add_argument('--config', dest='config_filename', action='store')
    parser.add_argument('--include-apt-clone', dest='do_apt_clone', action='store_true')
    parser.add_argument('--version', action='version', version=f'version: {version}')
    program_arguments = parser.parse_args()

    try:
        jf = open(program_arguments.config_filename)
        configuration = json.load(jf)
    except FileNotFoundError as e:
        print(f'configuration file [{program_arguments.config_filename}] not found')
        sys.exit()

    init(configuration, program_arguments)
    export_sql(configuration, program_arguments)
    if program_arguments.do_apt_clone:
        clone_apt(configuration, program_arguments)
    duplicity(configuration, program_arguments)
    rclone_copy(configuration, program_arguments)
    sys.exit()
