import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  insecureSkipTLSVerify: true,
  vus: 10,
  duration: '10s',
};

export default function () {
  const headers = {
    Host: 'itsup.srv.example.com',
  };
  const res = http.get(
    'http://192.168.1.30:8888/projects?apikey=xxx',
    // 'https://192.168.1.30:8443/projects?apikey=xxx',
    // 'https://itsup.srv.example.com/projects?apikey=xxx',
    { headers, insecureSkipTLSVerify: true }
  );
  check(res, { 'status was 200': (r) => r.status == 200 });
  sleep(0.01);
}
