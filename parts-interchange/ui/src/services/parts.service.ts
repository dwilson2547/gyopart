import { Injectable } from "@angular/core";
import { HttpClient, HttpParams } from "@angular/common/http";
import { environment } from "src/environments/environment";
import { PageRequest } from "src/models/PageRequest";
import { Observable, map } from "rxjs";

@Injectable()
export class PartsService {
    constructor(private http: HttpClient) { }

    get_parts_paged(payload: PartsPageRequest): Observable<any> {
        return this.http.post(environment.api_url + '/parts/parts', payload)
    }

    get_part(part_id: number): Observable<any> {
        return this.http.get(environment.api_url + '/parts/part/' + part_id)
    }

    get_compatible_cars(part_id: number, payload: CompatibleCarsRequest): Observable<any> {
        return this.http.post(environment.api_url + '/parts/compatible_cars/' + part_id, payload)
    }
}

export class PartsPageRequest extends PageRequest {
    car_id: number;
    filterStr: string;
    constructor(car_id: number, page: number, per_page: number, sort_col: string, sort_dir: string, filterStr: string = '') {
        super(page, per_page, sort_col, sort_dir);
        this.car_id = car_id;
        this.filterStr = filterStr;
    }
}

export class CompatibleCarsRequest extends PageRequest {
    part_id: number;
    filterStr: string;
    constructor(part_id: number, page: number, per_page: number, sort_col: string, sort_dir: string, filterStr: string = '') {
        super(page, per_page, sort_col, sort_dir);
        this.part_id = part_id;
        this.filterStr = filterStr;
    }
}

export class PartsPageResponse {
    items: Array<any> = [];
    has_next: boolean = true;
    has_prev: boolean = true;
    next_num: number = 2;
    prev_num: number = 1;
    page: number = 1;
    per_page: number = 30;
    pages: number = 0;
    total: number = 0;
}