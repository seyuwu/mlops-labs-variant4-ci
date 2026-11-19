# Git и CI/CD

Вариант 4: система логирования с уровнями debug, info, warn и error. Логи записываются по дням; при превышении заданного размера файл переименовывается с порядковым номером. Также сохранены арифметические функции из общего задания по Git.

```bash
npm run lint
npm test
npm run build
npm start
docker build -t git-cicd-lab .
docker run --rm git-cicd-lab
```

Workflow GitHub Actions запускает проверки для нескольких версий Node.js и собирает образ только после успешного завершения проверок.

Пример использования:

```js
const { createLogger } = require('./src/logger');
const log = createLogger({ directory: './logs', minLevel: 'info', maxBytes: 1024 * 1024 });
log.info('Приложение запущено');
log.warn('Пример предупреждения');
```
