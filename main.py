# -*- encoding: utf-8 -*-

import settings
import json
import urllib
import requests
import datetime
import base64
import time
import pyaml
import went
from urlparse import urlparse
from redis import StrictRedis
from flask import Flask, session, jsonify, redirect, request, render_template, abort

app = Flask(__name__)
app.secret_key = settings.GITHUB_APP_STATE
app.debug = True

redis = StrictRedis.from_url(settings.REDIS_URL)

@app.route('/')
def index():
        url = 'https://github.com/login/oauth/authorize'
        data = {
            'client_id': settings.GITHUB_APP_ID,
            'scope': 'user,public_repo,repo',
            'state': settings.GITHUB_APP_STATE
        }
        github_url = url + '?' + urllib.urlencode(data)
        return render_template('index.html', github_url=github_url)

@app.route('/github')
def github_redirect():
    if request.args.get('state') != settings.GITHUB_APP_STATE:
        return redirect('/')
    r = requests.post('https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json', 'Content-type': 'application/json'},
        data=json.dumps({
          'client_id': settings.GITHUB_APP_ID,
          'client_secret': settings.GITHUB_APP_SECRET,
          'code': request.args['code'],
        }))
    try:
        session['token'] = json.loads(r.text)['access_token']
        return redirect('/choose_repo')
    except KeyError:
        return redirect('/')

@app.route('/choose_repo')
def choose_repo():
    r = requests.get('https://api.github.com/user/repos',
        params={'access_token': session['token'],
                'per_page': 100})

    return render_template('choose_repo.html', repos=r.json())

@app.route('/choosed', methods=['POST'])
def choosed_repo():
    repo = request.form['repo']
    site = request.form['site']

    psite = urlparse(site)
    site = psite.netloc + '/' + '/'.join(filter(bool, psite.path.split('/')))

    redis.set(site, repo)
    redis.set(repo, session['token'])
    return render_template('ok.html')

@app.route('/webmentions/', methods=['POST'])
def webmention_endpoint():
    source = request.form['source']
    target = request.form['target']

    # test various combinations of the url to see what is the baseurl
    # and what is the path of the target post.
    # for example:
    # banana.com/ - blog/posts/sorvete-de-banana.html
    # banana.com/blog/ - posts/sorvete-de-banana.html
    ptarget = urlparse(target)
    pathparts = filter(bool, ptarget.path.split('/'))
    possible_sites = []
    possible_paths = []
    for i in range(len(pathparts)):
        possible_site_url = ptarget.netloc + '/' + '/'.join(pathparts[:i])
        possible_path = '/'.join(pathparts[i:])

        possible_sites.append(possible_site_url)
        possible_paths.append(possible_path)

    for i, repo in enumerate(redis.mget(possible_sites)):
        if repo:
            path = possible_paths[i]
            token = redis.get(repo)
            break
    else:
        abort(500)

    # parse the webmention
    try:
        webmention = went.Webmention(url=source, target=target)
    except (went.NoContent, went.NoURLInSource):
        webmention = None
    if not webmention or not hasattr(webmention, 'body'):
        print 'request failed: 400'
        print request.url
        print request.form
        return abort(400)

    # create the webmention file with its yaml frontmatter
    body = webmention.body

    # jekyll doesn't support yaml trees
    metadata = {
        'date': webmention.date,
        'source': webmention.url or source, # jekyll reservers the '.url' attr
        'name': webmention.name,
        'target': request.form['target'],
    }
    try: metadata['author_url'] = webmention.author.url
    except: pass
    try: metadata['author_name'] = webmention.author.name
    except: pass
    try: metadata['author_image'] = webmention.author.photo
    except: pass

    wm_file = u'---\n%s---\n%s' % (pyaml.dump(metadata), body)

    if u'…' in path:
        return 'not ok'

    # commit the webmention file at the github repo
    url = 'https://api.github.com/repos/' + repo + '/contents/_webmentions/' + path + '/' + string(int(time.time())) + '.md'
    content = base64.b64encode(wm_file.encode('utf-8'))
    data = {
        'content': content,
        'message': 'webmention from ' + source,
        'committer': {
            'name': 'Jekmention',
            'email': 'jekmention@jekmentions.alhur.es'
        }
    }
    r = requests.put(url, params={'access_token': token}, data=json.dumps(data))

    return 'ok'

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0')
