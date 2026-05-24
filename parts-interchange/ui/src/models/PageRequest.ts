export class PageRequest {
    page: number;
    per_page: number;
    sort_col: string;
    sort_dir: string;

    constructor(page: number, per_page: number, sort_col: string, sort_dir: string) {
        this.page = page;
        this.per_page = per_page;
        this.sort_col = sort_col;
        this.sort_dir = sort_dir;
    }

    toString() {
        return JSON.stringify(this)
    }
}