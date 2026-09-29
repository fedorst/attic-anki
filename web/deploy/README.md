# Deploying to sonad.fedor.ee

The same setup as illumine.fedor.ee. On every push to `main` that touches
`web/`, `.github/workflows/web.yml` validates the deck, runs the tests,
builds `dist/index.html` (the single-file static build) and rsyncs it to the
droplet as `sonad-deploy@164.92.234.72`. nginx (the Docker one in
`/home/fedor/bevy_md_sim`) serves it. Until the secret below exists, the deploy
job only prints a notice and skips.

## One-time setup

**1. DNS.** Add an `A` record `sonad.fedor.ee → 164.92.234.72`.

**2. Deploy user and web root** (on the droplet):

```bash
sudo mkdir -p /var/www/sonad.fedor.ee
sudo adduser --disabled-password --gecos "" sonad-deploy
sudo chown sonad-deploy: /var/www/sonad.fedor.ee
```

Make a key pair (anywhere, e.g. your laptop):

```bash
ssh-keygen -t ed25519 -N "" -C sonad-deploy -f sonad_deploy
```

Restrict that key to rsync into the web root, the same way `illumine-deploy`
is restricted. Copy its line and change the directory:

```bash
sudo cat ~illumine-deploy/.ssh/authorized_keys          # see how it's done there
sudo -u sonad-deploy mkdir -p -m 700 ~sonad-deploy/.ssh
echo "command=\"rrsync /var/www/sonad.fedor.ee\",restrict $(cat sonad_deploy.pub)" \
  | sudo -u sonad-deploy tee ~sonad-deploy/.ssh/authorized_keys
```

**3. nginx + certificate** (in `/home/fedor/bevy_md_sim`):

- In `compose.yml`, under the `nginx` service's `volumes:`, add
  `- /var/www/sonad.fedor.ee:/var/www/sonad.fedor.ee:ro`.
- Append **only the port-80 `server` block** from `nginx-sonad.conf` to
  `nginx/nginx.conf`. nginx won't start with the 443 block before the certificate
  exists.
- Then:

```bash
docker compose up -d nginx                                   # recreate with the new volume
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d sonad.fedor.ee
```

- Append the 443 block from `nginx-sonad.conf`, then
  `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload`.

**4. GitHub secret.** In `fedorst/attic-anki` → Settings → Secrets and
variables → Actions, add `SONAD_DEPLOY_SSH_KEY` with the contents of the
private key `sonad_deploy`. Then re-run the latest `web` workflow on `main`.
