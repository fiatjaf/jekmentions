# -*- encoding: utf-8 -*-

import settings
import json
import urllib
import requests
import datetime
import hashlib
import base64
import pyaml
import went
from urlparse import urlparse
from redis import StrictRedis
from flask import Flask, session, jsonify, redirect, request, render_template, abort

app = Flask(__name__)
app.secret_key = 'JKBW,KQ4B,shwghg4hgbhgwhtqdbaskr34234257'
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
        params={'access_token': session['token']})

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
    webmention = went.Webmention(url=source, target=target)

    # create the webmention file with its yaml frontmatter
    body = webmention.body
    metadata = webmention.__dict__
    del metadata['summary']
    del metadata['body']
    metadata['source'] = metadata.pop('url') # jekyll reservers the '.url'
    try: metadata['author_url'] = metadata['author'].pop('url')
    except: pass
    try: metadata['author_name'] = metadata['author'].pop('name')
    except: pass
    try: metadata['author_image'] = metadata['author'].pop('photo')
    except: pass
    del metadata['author'] # jekyll doesn't support yaml trees

    wm_file = u'---\n%s---\n%s' % (pyaml.dump(metadata), body)

    # commit the webmention file at the github repo
    r = requests.put(
        'https://api.github.com/repos/' + repo + '/contents/_webmentions/' + path + '/' + hashlib.md5(metadata['source']).hexdigest() + '.md',
        params={'access_token': token},
        data=json.dumps({
            'content': base64.b64encode(wm_file.encode('utf-8')),
            'message': 'webmention from ' + source,
            'committer': {
                'name': 'Jekmention',
                'email': 'jekmention@jekmentions.alhur.es'
            }
        })
    )

    return r.text
    return 'ok'

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0')
