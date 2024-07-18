from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from Chat import AIsessions
from werkzeug.utils import secure_filename
import os
import shutil
from flask import Flask, request, session, redirect, url_for, render_template, stream_with_context, Response,flash,jsonify
from utils.tools import allowed_file

app = Flask(__name__)
app.secret_key = '7890qwer'

# MySQL 配置
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '123456'
app.config['MYSQL_DB'] = 'userdb'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PORT'] = 3306
app.config['SAVE_PATH'] = "./uploaded"
app.config['VECTOR_PATH'] = "./vectorstore"

mysql = MySQL(app)
ai_session = AIsessions()

@app.route('/')
def home():
    return render_template('index.html')

#注册
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            hashed_password = generate_password_hash(password)

            cursor = mysql.connection.cursor()
            
            app.logger.debug(f'Executing INSERT INTO users (username, password) VALUES ({username}, [hashed_password])')
            cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, hashed_password))
            mysql.connection.commit()
            cursor.close()
            flash('您已成功注册！', 'success')
            
            #为用户创建文件夹
            userdir = app.config['SAVE_PATH'] + "/" +username
            session['userdir'] = userdir
            os.mkdir(session['userdir'])
            vecdir = app.config['VECTOR_PATH'] + "/" +username
            os.mkdir(vecdir)
            
            return redirect(url_for('login'))
        except Exception as e:
            app.logger.error(f'Error during registration: {str(e)}')
            flash(f'错误: {str(e)}', 'danger')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # try:
            username = request.form['username']
            password = request.form['password']

            cursor = mysql.connection.cursor()
            app.logger.debug(f'Executing SELECT * FROM users WHERE username = {username}')
            cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
            user = cursor.fetchone()
            cursor.close()

            if user and check_password_hash(user[2], password):
                session['username'] = user[1]
                session["userroot"] = app.config['SAVE_PATH']+"/"+session["username"]
                #个人专属AI
                if ai_session.get_user(username) == None:
                    ai_session.add_user(username=username,mysql=mysql,app=app)
                flash('您已成功登录！', 'success')
                session["from_login"] = True
                return redirect(url_for('profile'))
            else:
                flash('用户名或密码无效', 'danger')
        # except Exception as e:
        #     app.logger.error(f'Error during login: {str(e)}')
        #     flash(f'错误: {str(e)}', 'danger')

    return render_template('login.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        try:
            user = request.form['username']
            password = request.form['password']

            if user=='admin' and password=='admin':
                session['is_admin'] = True
                flash('您已成功登录！', 'success')
                return redirect(url_for('admin_panel'))
            else:
                flash('用户名或密码无效', 'danger')
        except Exception as e:
            app.logger.error(f'Error during login: {str(e)}')
            flash(f'错误: {str(e)}', 'danger')

    return render_template('admin_login.html')

# 新增管理员面板路由
@app.route('/admin_panel', methods=['GET'])
def admin_panel():
    if 'is_admin' not in session or not session['is_admin']:
        flash('您没有权限访问这个页面！', 'danger')
        return redirect(url_for('admin_login'))
    
    cursor = mysql.connection.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    cursor.close()
    files = os.listdir("./uploaded")
    add_files = os.listdir("./docs")
    
    return render_template('admin_panel.html', users=users, files = files, add_files = add_files)


@app.route('/profile', methods=['GET', 'POST'])
async def profile():
        
    if 'username' not in session:
        return redirect(url_for('login'))
    
    session['chat_history'] = ai_session.get_user(session["username"]).get_chat_record()

    return render_template('profile.html', username=session['username'], chat_history=session['chat_history'])

#作为流式返回的输出
@app.route('/stream_response')
def stream_response():
    user_input = request.args.get('user_input')
    return Response(stream_with_context(ai_session.get_user(session["username"]).answer(user_input)), mimetype='text/event-stream')

#上传文件
@app.route('/upload_file', methods=['GET', 'POST'])
def upload_file():
    session['inform'] = ''
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('没有文件部分', 'danger')
            return redirect(url_for('upload'))

        file = request.files['file']
        if file.filename == '':
            flash('没有选择文件', 'danger')
            return redirect(url_for('upload'))

        if file and allowed_file(file.filename):
            #上传文件
            filename = file.filename
            saved_file = session["userroot"]+"/"+filename
            file.save(saved_file)
            
            #更新session库
            ai_session.get_user(session["username"]).add_documents(new_doc=saved_file)
            session['inform'] = '上传成功！'
            flash('上传成功！', 'success')
            return redirect(url_for('profile'))
        else:
            flash('不允许的文件类型', 'danger')
            return redirect(url_for('upload'))

    return render_template('upload_file.html')
    
#获取上传后的文件
@app.route('/api/uploaded_files', methods=['GET'])
def get_uploaded_files():
    files = os.listdir(session["userroot"])
    file_list = [{'name': file} for file in files]
    return jsonify(file_list)

#删除用户文件
@app.route('/api/delete_file', methods=['DELETE'])
def delete_file():
    file_name = request.args.get('file_name')
    if not file_name:
        return jsonify({'error': 'file_name is required'}), 400

    file_path = session["userroot"] + "/" + file_name
    if os.path.exists(file_path):
        os.remove(file_path)
        ai_session.get_user(session["username"]).del_documents(file_path)
        print("删除成功！")
        return jsonify({'message': f'File {file_name} deleted successfully'}), 200
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/logout')
def logout():
    ai_session.get_user(session["username"]).del_chat_record()
    ai_session.rm_user(session["username"])
    session.pop('username', None)
    session.pop('chat_history',None)
    session.pop("userroot",None)
    flash('您已成功登出！', 'success')
    return redirect(url_for('login'))

#管理员删除用户
@app.route('/delete_user/<username>', methods=['POST'])
def delete_user(username):
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('DELETE FROM users WHERE username = %s', (username,))
        mysql.connection.commit()
        flash('用户删除成功！', 'success')
    except Exception as e:
        app.logger.error(f'Error during deleting user: {str(e)}')
        flash(f'删除失败: {str(e)}', 'danger')
    finally:
        cursor.close()
    return redirect(url_for('admin_panel'))

#管理员删除文件
@app.route('/delete_file/<filename>', methods=['POST'])
def delete_admin_file(filename):
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    try:
        os.remove("./uploaded/{}".format(filename))
        flash('文件删除成功！', 'success')
    except Exception as e:
        app.logger.error(f'Error during deleting user: {str(e)}')
        flash(f'删除失败: {str(e)}', 'danger')
    return redirect(url_for('admin_panel'))

#管理员删除已添加的文件
@app.route('/delete_added_file/<filename>', methods=['POST'])
def delete_added_file(filename):
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    try:
        os.remove("./docs/{}".format(filename))
        flash('文件删除成功！', 'success')
    except Exception as e:
        app.logger.error(f'Error during deleting user: {str(e)}')
        flash(f'删除失败: {str(e)}', 'danger')
    return redirect(url_for('admin_panel'))

#管理员添加文件
@app.route('/add_file/<filename>', methods=['POST'])
def add_file(filename):
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    try:
        # 定义源文件和目标文件的路径
        source = './uploaded/{}'.format(filename)
        destination = './docs/{}'.format(filename)
        # 拷贝文件
        shutil.move(source, destination)
        flash('文件删除成功！', 'success')
    except Exception as e:
        app.logger.error(f'Error during deleting user: {str(e)}')
        flash(f'删除失败: {str(e)}', 'danger')
    return redirect(url_for('admin_panel'))



if __name__ == '__main__':
    app.run(debug=False, threaded=False)
