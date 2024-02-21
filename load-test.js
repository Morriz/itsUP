import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  insecureSkipTLSVerify: true,
  stages: [
    // { duration: '30s', target: 20 },
    { duration: '0m20s', target: 1 },
    // { duration: '20s', target: 20 },
  ],
};

export default function () {
  const res = http.get(`https://hello.srv.instrukt.ai`);
  check(res, { 'status was 200': (r) => r.status == 200 });
  sleep(1);
}
